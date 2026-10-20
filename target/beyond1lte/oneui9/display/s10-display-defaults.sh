#!/system/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Seed model-specific stock geometry once per fresh userdata installation.
set -eu
case "$(getprop ro.product.model):$(getprop ro.product.device)" in
    SM-G970F:beyond0|SM-G970F:beyond0lte|SM-G973F:beyond1|SM-G973F:beyond1lte|SM-G975F:beyond2|SM-G975F:beyond2lte) ;;
    *) exit 0 ;;
esac
[ "$(getprop ro.build.version.sdk)" = 37 ] || exit 0
directory=/data/misc/s10-display-defaults
marker="$directory/applied-v1"
[ ! -f "$marker" ] || exit 0
export CLASSPATH=/system/framework/s10-display-defaults.jar
app_process /system/bin S10DisplayOverlay
preferred="$(cmd display get-user-preferred-display-mode 0)"
case "$preferred" in 'User preferred display mode: -1 -1 0.0'|'User preferred display mode: null')
    cmd display set-user-preferred-display-mode 1080 2280 60.000004 0
    preferred="$(cmd display get-user-preferred-display-mode 0)"
    case "$preferred" in 'User preferred display mode: 1080 2280 60.'*) ;; *) exit 1 ;; esac
    ;;
esac
# Keep subsequent user display/overlay choices, rather than forcing each boot.
mkdir -p "$directory"
chmod 700 "$directory"
printf '%s\n' 's10-display-defaults-v1' > "$marker"
chmod 600 "$marker"
