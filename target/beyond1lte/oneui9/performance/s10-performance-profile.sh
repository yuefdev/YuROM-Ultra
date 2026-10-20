#!/vendor/bin/sh
# The measured profile is valid only for this exact OC-capable boot image.
set -eu
SYS=/sys
STATE=/data/vendor/s10-performance
CONTROL=/data/system/artisan-control
BOOT=/dev/block/platform/13d60000.ufs/by-name/boot
BOOT_SHA=99bf2e7d589f9907e47861e1c8755264e32c39c108467b497f638aa93b4b7f10

state() { setprop vendor.s10.performance.state "$1"; }

compatible() {
    [ "$(id -u)" = 0 ] &&
    [ "$(getprop ro.product.model)" = SM-G973F ] &&
    [ "$(sha256sum "$BOOT" | cut -d ' ' -f 1)" = "$BOOT_SHA" ]
}

normal() {
    for domain in big mid lit g3d; do
        echo 0 > "$SYS/power/percent_margin/${domain}_margin_percent"
    done
    echo 156000 > "$SYS/kernel/gpu/gpu_min_clock"
    echo Interactive > "$SYS/kernel/gpu/gpu_governor"
    echo 650000 > "$SYS/kernel/gpu/gpu_max_clock"
    for cpu in 0 4 6; do
        path=$SYS/devices/system/cpu/cpufreq/policy$cpu
        echo 4000 > "$path/schedutil/up_rate_limit_us"
        echo 4000 > "$path/schedutil/down_rate_limit_us"
    done
    echo 1950000 > "$SYS/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
    echo 2314000 > "$SYS/devices/system/cpu/cpufreq/policy4/scaling_max_freq"
    echo 2730000 > "$SYS/devices/system/cpu/cpufreq/policy6/scaling_max_freq"
}

apply_profile() {
    lit_max=2106000; mid_max=2400000; big_max=3016000; gpu_max=806000; margin=-3
    # Start saved adaptive/stock modes without a static OC/UV interval while
    # the broker waits for this script's boot health window to complete.
    if [ -f "$CONTROL/performance-pending" ] || { [ -f "$CONTROL/performance.json" ] &&
        grep -Eq '"mode"[[:space:]]*:[[:space:]]*"(auto|oc|stock)"' "$CONTROL/performance.json"; }; then
        lit_max=1950000; mid_max=2314000; big_max=2730000; gpu_max=650000; margin=0
    fi
    for domain in big mid lit g3d; do
        case "$(cat "$SYS/power/percent_margin/${domain}_margin_percent")" in
            0|-1|-2|-3) ;; *) return 1 ;;
        esac
    done
    echo 87 > "$SYS/devices/platform/exynos-hiu/hiu/power_budget"
    echo 83000 > "$SYS/class/thermal/thermal_zone0/trip_point_2_temp"
    echo 83000 > "$SYS/class/thermal/thermal_zone1/trip_point_2_temp"
    echo 88000 > "$SYS/class/thermal/thermal_zone3/trip_point_2_temp"
    for cpu in 0 4 6; do
        path=$SYS/devices/system/cpu/cpufreq/policy$cpu
        [ "$(cat "$path/scaling_governor")" = schedutil ]
        up=4000
        [ "$cpu" = 6 ] || up=1000
        echo "$up" > "$path/schedutil/up_rate_limit_us"
        echo 4000 > "$path/schedutil/down_rate_limit_us"
        [ "$(cat "$path/schedutil/up_rate_limit_us")" = "$up" ]
    done
    echo 442000 > "$SYS/devices/system/cpu/cpufreq/policy0/scaling_min_freq"
    echo 507000 > "$SYS/devices/system/cpu/cpufreq/policy4/scaling_min_freq"
    echo 520000 > "$SYS/devices/system/cpu/cpufreq/policy6/scaling_min_freq"
    echo "$lit_max" > "$SYS/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
    echo "$mid_max" > "$SYS/devices/system/cpu/cpufreq/policy4/scaling_max_freq"
    echo "$big_max" > "$SYS/devices/system/cpu/cpufreq/policy6/scaling_max_freq"
    echo 156000 > "$SYS/kernel/gpu/gpu_min_clock"
    echo Interactive > "$SYS/kernel/gpu/gpu_governor"
    echo "$gpu_max" > "$SYS/kernel/gpu/gpu_max_clock"
    [ "$(cat "$SYS/kernel/gpu/gpu_max_clock")" = "$gpu_max" ]
    [ "$(cat "$SYS/kernel/gpu/gpu_governor")" = Interactive ]
    for domain in big mid lit g3d; do
        echo "$margin" > "$SYS/power/percent_margin/${domain}_margin_percent"
        [ "$(cat "$SYS/power/percent_margin/${domain}_margin_percent")" = "$margin" ]
    done
}

failed() {
    result=$?
    trap - EXIT HUP INT TERM
    set +e
    normal
    touch "$STATE/disabled"
    state failed
    exit "$result"
}

case "${1:-status}" in
    disable)
        [ -d "$STATE" ]
        touch "$STATE/disabled"
        compatible && normal
        state disabled
        exit
        ;;
    enable)
        compatible
        [ -d "$STATE" ]
        rm -f "$STATE/disabled" "$STATE/pending"
        ;;
    boot) ;;
    status)
        getprop vendor.s10.performance.state
        if [ -e "$STATE/disabled" ]; then echo automatic_application=disabled; else echo automatic_application=enabled; fi
        exit
        ;;
    *) exit 1 ;;
esac

[ "$(getprop sys.boot_completed)" = 1 ] || exit 1
if ! compatible; then state skipped-kernel; exit; fi
[ -d "$STATE" ]
if [ -e "$STATE/disabled" ]; then state disabled; exit; fi
if [ -e "$STATE/pending" ]; then
    touch "$STATE/disabled"
    normal
    state interrupted
    exit
fi
boot_id=$(cat /proc/sys/kernel/random/boot_id)
runtime=$(pidof system_server)
[ -n "$runtime" ]
printf '%s\n' "$boot_id" > "$STATE/pending"
trap failed EXIT
trap 'exit 1' HUP INT TERM
state applying
apply_profile
for interval in 1 2 3 4 5 6; do
    sleep 5
    [ ! -e "$STATE/disabled" ]
    [ "$(pidof system_server)" = "$runtime" ]
    [ "$(cat /proc/sys/kernel/random/boot_id)" = "$boot_id" ]
done
rm "$STATE/pending"
state applied
trap - EXIT HUP INT TERM
