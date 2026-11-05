#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only source and optional candidate checks for Astropart S10 targets.

No firmware download, root command, partition write, signing bypass, or
hardware-success inference is performed by this script.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

MIB = 1024 * 1024
MODEL_DEVICE = {"SM-G970F": "beyond0lte", "SM-G973F": "beyond1lte",
                "SM-G975F": "beyond2lte"}
# Model-specific image sizes must be measured before assigning PIT capacity.
PLANNING_MIB = {"system": 10240, "vendor": 2048}
S26_DONORS = [
    {"model": "SM-S942B", "build": "S942BXXU4ZZH6",
     "one_ui": "9", "status": "inherited pinned donor; not S26 Ultra"},
    {"model": "SM-S948B", "build": "S948BXXU5BZJA",
     "one_ui": "9", "status": "Samsung-published S26 Ultra update 2026-10-29"},
    {"model": "SM-S948B", "build": "S948BXXU6ZZK3",
     "one_ui": "9.5", "status": "reported internal test; NOT downloadable public donor"},
]
REQUIRED_PACKAGES = (
    "com.google.android.gms", "com.google.android.gsf",
    "com.android.vending", "com.sec.android.app.camera",
)
REQUIRED_S10PLUS_CUTOUT = (
    "M 0,0 H -93.14285714285714 V 40.57142857142857 H 0 V 0 Z @dp @right"
)


def package_names(path: Path) -> set[str]:
    """Read 'adb shell pm list packages' lines, ignoring blank/comment lines."""
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("package:"):
            line = line.removeprefix("package:")
        if not line or " " in line:
            raise ValueError("Malformed package-list line (expected a package id)")
        names.add(line)
    return names


def check_source(checkout: Path, model: str, package_list: Path | None = None,
                 image_dir: Path | None = None) -> dict:
    if model not in MODEL_DEVICE:
        raise ValueError("Unsupported target model")
    checkout = checkout.resolve()
    layout_file = checkout / "target/beyond1lte/oneui9/stock-layout.json"
    profiles_file = checkout / "target/beyond1lte/oneui9/display/profiles.json"
    layout = json.loads(layout_file.read_text(encoding="utf-8"))
    profiles = json.loads(profiles_file.read_text(encoding="utf-8"))["models"]
    if profiles[model]["device"] != MODEL_DEVICE[model]:
        raise ValueError("Display profile and device registry disagree")
    old_sizes = {name: layout["partitions"][name]["bytes"] // MIB
                 for name in ("system", "vendor")}
    if any(layout["partitions"][name]["bytes"] % MIB for name in old_sizes):
        raise ValueError("Stock layout needs exact MiB sizes")
    if layout.get("repartition") is not False:
        raise ValueError("Unexpected repartitioned source baseline")
    obsolete_scripts = sorted(str(path.relative_to(checkout))
                              for base in ("unica", "platform", "target")
                              for path in (checkout / base).rglob("debloat.sh"))
    obsolete_modules = sorted(str(path.relative_to(checkout))
                              for base in ("unica/patches", "unica/mods")
                              for path in (checkout / base).iterdir()
                              if path.is_dir() and path.name.lower() in
                              ("_debloat", "debloat"))
    installer = (checkout / "target/beyond1lte/oneui9/installer/update-binary").read_text()
    init = (checkout / "target/beyond1lte/oneui9/display/s10-display-defaults.rc").read_text()
    geometry = profiles["SM-G975F"]["cutout"]
    source_checks = {
        "automatic_debloat_removed": not (obsolete_scripts or obsolete_modules),
        "installer_fd_uses_procfs": '>"/proc/self/fd/$OUTFD"' in installer,
        "installer_visible_stages": all(f"[{n}/6]" in installer for n in range(1, 7)),
        "installer_preserves_partition_check": 'Unsupported $part partition size' in installer,
        "installer_preserves_readback_check": "Readback mismatch" in installer,
        "s10_display_service_shell_domain": "seclabel u:r:shell:s0" in init,
        "s10plus_cutout_matches_reference": geometry == REQUIRED_S10PLUS_CUTOUT,
    }
    report = {
        "schema": 1, "project": "Astropart", "model": model,
        "device": MODEL_DEVICE[model], "scope": "HOST SOURCE AUDIT ONLY",
        "phone_boot_confirmed": False, "flash_ready": False,
        "source_checks": source_checks,
        "remaining_debloat_scripts": obsolete_scripts,
        "remaining_debloat_modules": obsolete_modules,
        "capacity_mib": {
            "baseline": old_sizes,
            "proposal": PLANNING_MIB,
            "extra_system_and_vendor": sum(PLANNING_MIB.values()) - sum(old_sizes.values()),
            "proposal_is_not_measured_image_size": True,
        },
        "donor_options": S26_DONORS,
        "issues": {
            "gms_crashes": "runtime logs and APK/dependency verification needed",
            "general_system_bugs": "physical boot + logcat + HAL/VINTF tests needed",
            "kernelsu_next_susfs": "requires a verified S10+ kernel source build",
            "samsung_stock_apps": "deletion scripts removed; missing donor packages still need integration",
            "galaxy_ai": "requires signed packages/frameworks and model-specific acceptance",
            "repartitioner": "not implemented; PIT writes must never use estimates",
            "modern_samsung_camera": "old S10 APK remains; S26 Ultra adapter not proven",
            "s26_ultra_oneui_9_5": "only internal test build known; no verifiable public image",
        },
    }
    if package_list:
        installed = package_names(package_list)
        report["package_inventory"] = {
            "source": "supplied pm-list text; package presence is not crash-free proof",
            "present": sorted(set(REQUIRED_PACKAGES) & installed),
            "missing": sorted(set(REQUIRED_PACKAGES) - installed),
        }
    if image_dir:
        image_dir = image_dir.resolve()
        sizes = {}
        for name in ("system", "vendor"):
            image = image_dir / (name + ".img")
            if not image.is_file():
                sizes[name] = {"error": "image not provided"}
                continue
            actual_bytes = image.stat().st_size
            sizes[name] = {
                "file_bytes": actual_bytes,
                "fits_baseline_capacity": actual_bytes <= layout["partitions"][name]["bytes"],
                "fits_proposed_capacity": actual_bytes <= PLANNING_MIB[name] * MIB,
                "actual_file_size_not_used_space": True,
            }
        report["image_sizes"] = sizes
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--model", choices=MODEL_DEVICE, default="SM-G975F")
    parser.add_argument("--package-list", type=Path,
                        help="Optional package names captured from a booted phone")
    parser.add_argument("--image-dir", type=Path,
                        help="Optional built .img files; only measures, never writes")
    parser.add_argument("--strict", action="store_true", help="fail for source failures/missing required packages")
    args = parser.parse_args()
    try:
        report = check_source(args.checkout, args.model, args.package_list, args.image_dir)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Astropart source audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and (not all(report["source_checks"].values())
                        or report.get("package_inventory", {}).get("missing")
                        or any(v.get("fits_proposed_capacity") is False
                               for v in report.get("image_sizes", {}).values())):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
