#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the actual donor-profile adaptation and reject incompatible inputs."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--stock-vendor", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "s10_schedtune.py"
    spec = importlib.util.spec_from_file_location("s10_schedtune", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = json.loads((args.system / "etc/task_profiles.json").read_text())
    original_bytes = {name: (args.system / name).read_bytes()
                      for name in ("etc/cgroups.json", "etc/task_profiles.json")}
    with tempfile.TemporaryDirectory(prefix="s10-schedtune-") as temporary:
        base = Path(temporary)
        vendor = base / "vendor"
        for name in ("etc/init/init.exynos9820.rc", "etc/hyper/config_chipset.json"):
            destination = vendor / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.stock_vendor / name, destination)
        metadata = module.configure_legacy_schedtune(args.system, vendor)
        adapted = json.loads((vendor / "etc/task_profiles.json").read_text())
        defaults = {p["Name"]: p for p in original["Profiles"]}
        merged = copy.deepcopy(defaults)
        for profile in adapted["Profiles"]:
            assert profile["Actions"][:-1] == defaults[profile["Name"]]["Actions"]
            assert profile["Actions"][-1]["Params"]["Controller"] == "schedtune"
            merged[profile["Name"]] = profile
        for name, profile in defaults.items():
            if name not in {p["Name"] for p in adapted["Profiles"]}:
                assert merged[name] == profile
        # Exercise the actual profile graph used during app state transitions.
        aggregates = {p["Name"]: p["Profiles"] for p in original["AggregateProfiles"]}
        for aggregate, expected in (("SCHED_SP_BACKGROUND", "background"),
                                    ("SCHED_SP_FOREGROUND", "foreground"),
                                    ("SCHED_SP_TOP_APP", "top-app"),
                                    ("SCHED_SP_BACKGROUND", "background")):
            groups = [a["Params"]["Path"] for name in aggregates[aggregate]
                      for a in merged[name]["Actions"]
                      if a["Name"] == "JoinCgroup" and a["Params"]["Controller"] == "schedtune"]
            assert groups == [expected], (aggregate, groups)
        assert len(metadata["files"]) == 3
        for name, data in original_bytes.items():
            assert (args.system / name).read_bytes() == data
        try:
            module.configure_legacy_schedtune(args.system, vendor)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Must not overwrite vendor overrides")
        broken = base / "broken-system/etc"
        broken.mkdir(parents=True)
        (broken / "cgroups.json").write_bytes(original_bytes["etc/cgroups.json"])
        changed = copy.deepcopy(original)
        next(p for p in changed["Profiles"] if p["Name"] == "MaxPerformance")["Actions"] = []
        (broken / "task_profiles.json").write_text(json.dumps(changed))
        for name in metadata["files"]:
            (vendor / name).unlink()
        try:
            module.configure_legacy_schedtune(base / "broken-system", vendor)
        except RuntimeError:
            assert all(not (vendor / name).exists() for name in metadata["files"])
        else:
            raise AssertionError("Must reject changed donor profiles before writing")
    print("Passed donor action preservation, real aggregate transitions, overwrite and input guards.")


if __name__ == "__main__":
    main()
