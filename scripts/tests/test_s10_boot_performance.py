#!/usr/bin/env python3
"""Run the real boot script against isolated sysfs fixtures and command stubs."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "target/beyond1lte/oneui9/performance/s10-performance-profile.sh"
SHA = "99bf2e7d589f9907e47861e1c8755264e32c39c108467b497f638aa93b4b7f10"


class Fixture:
    def __init__(self, root):
        self.root = root
        self.sys = root / "sys"
        self.state = root / "state"
        self.state.mkdir()
        self.commands = root / "bin"
        self.commands.mkdir()
        self.env = {**os.environ, "PATH": f"{self.commands}:/usr/bin:/bin",
                    "FIXTURE": str(root), "FAKE_KERNEL": SHA}
        (root / "runtime").write_text("2477\n")
        self.stub("id", "echo 0")
        self.stub("getprop", 'case "$1" in ro.product.model) echo SM-G973F ;; sys.boot_completed) echo 1 ;; esac')
        self.stub("setprop", 'printf "%s %s\\n" "$1" "$2" >> "$FIXTURE/properties"')
        self.stub("sha256sum", 'printf "%s  %s\\n" "$FAKE_KERNEL" "$1"')
        self.stub("pidof", '/bin/cat "$FIXTURE/runtime"')
        self.stub("sleep", 'if [ "${FAKE_RUNTIME_RESTART:-0}" = 1 ]; then echo 2488 > "$FIXTURE/runtime"; fi')
        self.stub("cat", '''if [ "${FAKE_READBACK_FAILURE:-0}" = 1 ]; then
    case "$1" in */big_margin_percent)
        if [ "$(/bin/cat "$1")" = -3 ]; then echo 0; exit; fi ;;
    esac
fi
exec /bin/cat "$@"''')
        for domain in ("big", "mid", "lit", "g3d"):
            self.put(f"power/percent_margin/{domain}_margin_percent", "0")
        for cpu in (0, 4, 6):
            for name, value in (("scaling_governor", "schedutil"), ("scaling_min_freq", "0"),
                                ("scaling_max_freq", "0"), ("schedutil/up_rate_limit_us", "4000"),
                                ("schedutil/down_rate_limit_us", "4000")):
                self.put(f"devices/system/cpu/cpufreq/policy{cpu}/{name}", value)
        for name in ("gpu_min_clock", "gpu_max_clock", "gpu_governor"):
            self.put(f"kernel/gpu/{name}", "0")
        self.put("devices/platform/exynos-hiu/hiu/power_budget", "87")
        for zone in (0, 1, 3):
            self.put(f"class/thermal/thermal_zone{zone}/trip_point_2_temp", "83000")
        text = SOURCE.read_text().replace("SYS=/sys", f"SYS='{self.sys}'")
        text = text.replace("STATE=/data/vendor/s10-performance", f"STATE='{self.state}'")
        text = text.replace("CONTROL=/data/system/artisan-control", f"CONTROL='{root / 'control'}'")
        text = text.replace("BOOT=/dev/block/platform/13d60000.ufs/by-name/boot", f"BOOT='{root / 'boot'}'")
        self.script = root / "profile.sh"
        self.script.write_text(text)

    def stub(self, name, text):
        path = self.commands / name
        path.write_text("#!/bin/sh\n" + text + "\n")
        path.chmod(0o755)

    def put(self, path, value):
        target = self.sys / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + "\n")

    def get(self, path):
        return (self.sys / path).read_text().strip()

    def run(self, action, success=True):
        result = subprocess.run(["sh", str(self.script), action], env=self.env, capture_output=True, text=True)
        assert (result.returncode == 0) == success, (result.returncode, result.stdout, result.stderr)

    def property(self):
        return (self.root / "properties").read_text().splitlines()[-1].split()[1]

    def normal(self):
        assert all(self.get(f"power/percent_margin/{domain}_margin_percent") == "0"
                   for domain in ("big", "mid", "lit", "g3d"))
        assert self.get("devices/system/cpu/cpufreq/policy6/scaling_max_freq") == "2730000"
        assert self.get("kernel/gpu/gpu_max_clock") == "650000"


def main():
    with tempfile.TemporaryDirectory(prefix="s10-boot-performance-") as directory:
        root = Path(directory)
        fixtures = []
        for index in range(9):
            path = root / str(index)
            path.mkdir()
            fixtures.append(Fixture(path))
        normal, wrong_kernel, interrupted, bad_readback, runtime_restart, adaptive, stock, oc, control_pending = fixtures
        normal.run("boot")
        assert normal.property() == "applied"
        assert not (normal.state / "pending").exists()
        assert all(normal.get(f"power/percent_margin/{domain}_margin_percent") == "-3"
                   for domain in ("big", "mid", "lit", "g3d"))
        assert normal.get("devices/system/cpu/cpufreq/policy6/scaling_max_freq") == "3016000"
        assert all(normal.get(f"devices/system/cpu/cpufreq/policy{cpu}/schedutil/up_rate_limit_us") == "1000"
                   for cpu in (0, 4))
        normal.run("disable")
        normal.normal()
        normal.run("boot")
        assert normal.property() == "disabled"
        normal.normal()
        normal.run("enable")
        assert normal.property() == "applied" and not (normal.state / "disabled").exists()
        wrong_kernel.env["FAKE_KERNEL"] = "0" * 64
        wrong_kernel.run("boot")
        assert wrong_kernel.property() == "skipped-kernel"
        assert wrong_kernel.get("devices/system/cpu/cpufreq/policy6/scaling_max_freq") == "0"
        assert not (wrong_kernel.state / "pending").exists()
        (interrupted.state / "pending").write_text("previous-boot\n")
        interrupted.run("boot")
        interrupted.normal()
        assert interrupted.property() == "interrupted" and (interrupted.state / "disabled").exists()
        bad_readback.env["FAKE_READBACK_FAILURE"] = "1"
        bad_readback.run("boot", success=False)
        bad_readback.normal()
        assert bad_readback.property() == "failed" and (bad_readback.state / "disabled").exists()
        runtime_restart.env["FAKE_RUNTIME_RESTART"] = "1"
        runtime_restart.run("boot", success=False)
        runtime_restart.normal()
        assert runtime_restart.property() == "failed" and (runtime_restart.state / "disabled").exists()
        for fixture, mode in ((adaptive, "auto"), (stock, "stock"), (oc, "oc")):
            (fixture.root / "control").mkdir()
            (fixture.root / "control/performance.json").write_text('{"mode":"' + mode + '","undervolt":3}')
            fixture.run("boot")
            fixture.normal()
            assert fixture.property() == "applied"
        (control_pending.root / "control").mkdir()
        (control_pending.root / "control/performance-pending").write_text("previous control crash")
        control_pending.run("boot")
        control_pending.normal()
        assert control_pending.property() == "applied"
    print("PASS: boot profile, disabled/re-enable, wrong kernel, interrupted boot, readback/restart rollback, saved auto/stock/OC and controller-crash cold starts")


if __name__ == "__main__":
    main()
