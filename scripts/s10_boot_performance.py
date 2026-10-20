#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage the checksum-pinned S10 boot performance profile and oneshot service."""

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "target/beyond1lte/oneui9/performance"
FILES = {
    "etc/init/02-s10-performance.rc": "02-s10-performance.rc",
    "etc/s10-performance-profile.sh": "s10-performance-profile.sh",
}


def configure_performance_control(vendor, model, boot_sha):
    from s10_models import MODELS
    if model not in MODELS or len(boot_sha) != 64 or any(c not in "0123456789abcdef" for c in boot_sha):
        raise RuntimeError("A registered model and full boot SHA256 are required")
    name = "etc/s10-performance-control.json"
    target = vendor / name
    if target.exists():
        raise RuntimeError("Unexpected existing adaptive performance profile")
    label = os.getxattr(vendor / "etc/init/init.exynos9820.rc", "security.selinux")
    target.write_text(json.dumps({"schema": 1, "model": model, "boot_sha256": boot_sha,
                                  "maximum_undervolt_percent": 3, "controller": "local-thermal-load-battery"}, indent=2) + "\n")
    os.chown(target, 0, 0)
    os.chmod(target, 0o644)
    os.setxattr(target, "security.selinux", label)
    return {name: {"sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "uid": 0, "gid": 0,
                   "mode": "0644", "selinux": label.rstrip(b"\0").decode()}}


def configure_boot_performance(vendor, reference_vendor=None, model="SM-G973F", kernel=None):
    boot_sha = "99bf2e7d589f9907e47861e1c8755264e32c39c108467b497f638aa93b4b7f10"
    if model != "SM-G973F":
        from s10_models import MODELS, layout_for
        if (model not in MODELS or not kernel or kernel.get("model") != model
                or kernel.get("performance_source_patch_sha256") != "6d353b6bc4d6af95d4ef9215f2b80825593dddfb2ac66efffdd38bca6ab654e5"
                or kernel.get("performance_profile") != {"cpu_oc_target_khz": 3016000, "gpu_oc_target_khz": 806000, "cluster_oc_requested": True}
                or kernel["images"]["boot.img"]["size"] != layout_for(model)["partitions"]["boot"]["bytes"]):
            raise RuntimeError("The model's reviewed OC source and complete boot image are required")
        boot_sha = kernel["images"]["boot.img"]["sha256"]
    reference = (reference_vendor or vendor) / "etc/init/init.exynos9820.rc"
    label = os.getxattr(reference, "security.selinux")
    for name in FILES:
        if (vendor / name).exists():
            raise RuntimeError(f"Unexpected existing S10 boot performance file: {name}")
    files = {}
    for name, source in FILES.items():
        target = vendor / name
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = (PAYLOAD / source).read_bytes()
        if source.endswith(".sh") and model != "SM-G973F":
            payload = payload.replace(b"SM-G973F", model.encode()).replace(
                b"99bf2e7d589f9907e47861e1c8755264e32c39c108467b497f638aa93b4b7f10", boot_sha.encode())
        target.write_bytes(payload)
        os.chown(target, 0, 0)
        os.chmod(target, 0o644)
        os.setxattr(target, "security.selinux", label)
        files[name] = {"sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                       "uid": 0, "gid": 0, "mode": "0644",
                       "selinux": label.rstrip(b"\0").decode()}
    files.update(configure_performance_control(vendor, model, boot_sha))
    return {"files": files, "inputs": {}, "trigger": "sys.boot_completed=1",
            "service": "vendor.s10-performance", "oneshot": True,
            "kernel_sha256": boot_sha,
            "voltage_margin_percent": -3, "m4_ceiling_khz": 3016000,
            "interrupted_application_disables_future_attempts": True,
            "charging_state_changed": False, "device_boot_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-vendor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = Path(os.environ.get("ARTISANROM_RECORDS_DIR", ROOT.parent / "ArtisanROM_records")).resolve()
    args.output = args.output.resolve()
    if records.is_relative_to(ROOT.resolve()) or not args.output.is_relative_to(records):
        parser.error("The bundle must be below the external records directory.")
    if args.output.is_relative_to(ROOT.resolve()):
        parser.error("The bundle must not be inside the source checkout.")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Use a new bundle directory under an existing parent.")
    args.output.mkdir()
    metadata = configure_boot_performance(args.output, args.stock_vendor)
    with (args.output / "manifest.json").open("x") as output:
        json.dump(metadata, output, indent=2)
        output.write("\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
