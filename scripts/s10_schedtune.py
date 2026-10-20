#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore HWC1's legacy scheduler interface using additive vendor profiles."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil


CPU_GROUPS = {
    "HighEnergySaving": ("background", "background"),
    "NormalPerformance": ("system", ""),
    "ServicePerformance": ("system-background", "background"),
    "HighPerformance": ("foreground", "foreground"),
    "HighPerformanceWI": ("foreground_window", "foreground"),
    "SystemServicePerformance": ("foreground", "foreground"),
    "MaxPerformance": ("top-app", "top-app"),
    "RealtimePerformance": ("rt", "top-app"),
}

INIT = """# Restore the legacy HWC1 scheduler groups before framework services start.
on init
    mkdir /dev/stune/foreground 0755 system system
    mkdir /dev/stune/background 0755 system system
    mkdir /dev/stune/top-app 0755 system system
    chown system system /dev/stune/tasks
    chown system system /dev/stune/cgroup.procs
"""
for _group in ("foreground", "background", "top-app"):
    INIT += (f"    chown system system /dev/stune/{_group}/tasks\n"
             f"    chown system system /dev/stune/{_group}/cgroup.procs\n")
INIT += """    write /dev/stune/foreground/schedtune.util_est_en 1
    write /dev/stune/foreground/schedtune.ontime_en 1
    write /dev/stune/top-app/schedtune.boost 5
    write /dev/stune/top-app/schedtune.prefer_idle 1
    write /dev/stune/top-app/schedtune.prefer_perf 0
    write /dev/stune/top-app/schedtune.util_est_en 1
    write /dev/stune/top-app/schedtune.ontime_en 1
"""


def configure_legacy_schedtune(system, vendor):
    """Keep donor CPU actions and add the matching stock S10 SchedTune group."""
    cgroups = json.loads((system / "etc/cgroups.json").read_text())
    profiles = json.loads((system / "etc/task_profiles.json").read_text())
    stock_init = vendor / "etc/init/init.exynos9820.rc"
    reference = vendor / "etc/hyper/config_chipset.json"
    stock_text = stock_init.read_text()
    chipset = json.loads(reference.read_text())
    if (any(c["Controller"] == "schedtune" for c in cgroups["Cgroups"])
            or not any(r.get("BoostPath") == "/dev/stune/top-app/schedtune.boost"
                       for r in chipset["Resources"])
            or any(line not in stock_text for line in (
                "write /dev/stune/top-app/schedtune.boost 5",
                "write /dev/stune/top-app/schedtune.prefer_idle 1",
                "write /dev/stune/foreground/schedtune.util_est_en 1",
                "write /dev/stune/foreground/schedtune.ontime_en 1"))):
        raise RuntimeError("Expected HWC1 SchedTune ABI and donor without a legacy controller")
    overrides = []
    for name, (cpu, stune) in CPU_GROUPS.items():
        matches = [p for p in profiles["Profiles"] if p["Name"] == name]
        expected = {"Name": "JoinCgroup", "Params": {"Controller": "cpu", "Path": cpu}}
        if len(matches) != 1 or matches[0]["Actions"] != [expected]:
            raise RuntimeError(f"Unexpected donor CPU profile: {name}")
        profile = copy.deepcopy(matches[0])
        profile["Actions"].append({"Name": "JoinCgroup", "Params": {
            "Controller": "schedtune", "Path": stune}})
        overrides.append(profile)
    additions = {
        "etc/cgroups.json": json.dumps({"Cgroups": [{"Controller": "schedtune",
            "Path": "/dev/stune", "Mode": "0755", "UID": "system", "GID": "system"}]}, indent=2) + "\n",
        "etc/task_profiles.json": json.dumps({"Profiles": overrides}, indent=2) + "\n",
        "etc/init/00-s10-schedtune.rc": INIT,
    }
    for name in additions:
        destination = vendor / name
        if destination.exists() or not destination.parent.is_dir():
            raise RuntimeError(f"Unexpected existing vendor scheduler override: {name}")
    files = {}
    for name, text in additions.items():
        destination = vendor / name
        destination.write_text(text)
        os.chown(destination, 0, 0)
        os.chmod(destination, 0o644)
        label = os.getxattr(stock_init if name.endswith(".rc") else reference, "security.selinux")
        os.setxattr(destination, "security.selinux", label)
        files[name] = {"sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                       "mode": "0644", "uid": 0, "gid": 0,
                       "selinux": label.rstrip(b"\0").decode()}
    return {"controller": "schedtune", "groups": ["", "foreground", "background", "top-app"],
            "stock_top_app_boost": 5, "profiles": list(CPU_GROUPS), "files": files,
            "inputs": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
                ("/system/etc/cgroups.json", system / "etc/cgroups.json"),
                ("/system/etc/task_profiles.json", system / "etc/task_profiles.json"),
                ("/vendor/etc/init/init.exynos9820.rc", stock_init),
                ("/vendor/etc/hyper/config_chipset.json", reference))},
            "donor_cpu_actions_preserved": True, "frequency_limits_changed": False,
            "system_files_changed": False, "device_boot_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--stock-vendor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Use a new bundle directory under an existing parent.")
    for name in ("etc/init/init.exynos9820.rc", "etc/hyper/config_chipset.json"):
        destination = args.output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.stock_vendor / name, destination)
    metadata = configure_legacy_schedtune(args.system, args.output)
    with (args.output / "manifest.json").open("x") as output:
        json.dump(metadata, output, indent=2)
        output.write("\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
