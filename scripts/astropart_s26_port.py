#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a real S26 Ultra system + genuine G975F vendor staging tree.

Inputs are locally extracted firmware, not inferred from build strings.
This stage DOES NOT construct a boot-validated image or touch a phone.
It preserves the S26 Ultra framework and Camera APK, but a modern
camera/framework is not functionally ported until device acceptance passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from s10_models import MODELS, verify_family_stock
from prepare_oneui9_s10_candidate import properties, set_property
from prepare_s10_family_candidate import apply_features

MODEL = "SM-G975F"
DEVICE = "beyond2lte"
DONOR_MODEL = "SM-S948B"
# Official public One UI 9 / Android 17; 9.5 internal images are not available.
PUBLIC_BUILDS = frozenset(("S948BXXU5BZJA",))
SYSTEM_PATHS = ("system", "system_ext", "product")
GMS_DIR_NAMES = {
    "gms": ("PrebuiltGmsCore", "GmsCore", "GooglePlayServices"),
    "gsf": ("GoogleServicesFramework",),
    "play_store": ("Phonesky", "GooglePlayStore", "Vending"),
}
CAMERA_APK = "system/priv-app/SamsungCamera/SamsungCamera.apk"
CAMERA_LIBS = (
    "libMultiFrameProcessing10.camera.samsung.so",
    "libMultiFrameProcessing20.camera.samsung.so",
    "libMultiFrameProcessing20Day.camera.samsung.so",
    "vendor.samsung_slsi.hardware.iva@1.0.so",
    "vendor.samsung_slsi.hardware.MultiFrameProcessing20@1.0.so",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_single_property(path: Path, name: str) -> str:
    values = properties(path).get(name, [])
    if len(values) != 1:
        raise ValueError(f"Missing or repeated property {name} in {path}")
    return values[0]


def preflight_donor(donor: Path) -> dict:
    manifest = json.loads((donor / "input.json").read_text())
    if (manifest.get("model") != DONOR_MODEL or
            manifest.get("build") not in PUBLIC_BUILDS or
            manifest.get("kind") not in ("verified-oneui9-donor", "verified-s26-ultra-donor")):
        raise ValueError("S26 Ultra donor metadata is absent, incorrect, or not public One UI 9")
    image = donor / "images/system.img"
    expected = manifest.get("images", {}).get("system.img", {}).get("sha256")
    if not expected or not image.is_file() or digest(image) != expected:
        raise ValueError("S26 Ultra system image hash must match its provenance manifest")
    system = donor / "tree/system"
    if read_single_property(system / "build.prop", "ro.build.version.incremental") != manifest["build"]:
        raise ValueError("S26 Ultra donor version does not match the actual System image")
    if read_single_property(system / "build.prop", "ro.build.version.sdk") != "37":
        raise ValueError("Expected Android 17, SDK 37")
    if not (system / "framework/framework.jar").is_file():
        raise ValueError("Missing full S26 Ultra framework")
    if not (system / "product").is_dir() or not (system / "system_ext").is_dir():
        raise ValueError("Donor must include merged /product and /system_ext; no app debloating")
    return manifest


def inventory_packages(system: Path) -> dict:
    result = {}
    product = system / "product"
    for role, directories in GMS_DIR_NAMES.items():
        found = []
        for dirname in directories:
            for root in (product, system / "system_ext", system):
                for category in ("app", "priv-app"):
                    directory = root / category / dirname
                    if directory.is_dir() and any(directory.glob("*.apk")):
                        found.append(str(directory.relative_to(system)))
        result[role] = sorted(set(found))
    camera = system / CAMERA_APK
    result["modern_camera"] = [CAMERA_APK] if camera.is_file() else []
    result["camera_apk_sha256"] = digest(camera) if camera.is_file() else None
    # Presence alone is NOT evidence of signature compatibility or runtime GMS.
    return result


def update_model_identity(system: Path) -> dict:
    updated = []
    for partition in SYSTEM_PATHS:
        prop = (system / "build.prop" if partition == "system" else
                system / partition / "etc/build.prop")
        if not prop.is_file():
            raise ValueError(f"Missing donor {partition} build.prop")
        for key, value in (
            ("model", MODEL), ("device", "beyond2"),
            ("name", "beyond2ltexx"),
        ):
            entry = f"ro.product.{partition}.{key}"
            set_property(prop, entry, value)
            updated.append(entry)
    return {"model": MODEL, "properties_changed": updated}


def inject_stock_camera_support(system: Path, stock_system: Path) -> dict:
    installed = {}
    for arch in ("lib", "lib64"):
        for name in CAMERA_LIBS:
            source = stock_system / arch / name
            target = system / arch / name
            if not source.is_file():
                raise ValueError("G975F camera HAL support is missing: " + str(source))
            if target.exists():
                # Do not overwrite different modern donor libraries or symlinks.
                if target.is_symlink() or digest(target) != digest(source):
                    raise ValueError("Donor/native camera library collision: " + str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            installed[str(target.relative_to(system))] = digest(target)
    return installed


def prepare(donor: Path, stock: Path, kernel: Path, output: Path,
            display_bundle: Path | None = None) -> dict:
    if os.geteuid() != 0:
        raise ValueError("Root required to preserve Android ownership and SELinux labels")
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Candidate destination must be new and its parent must exist")
    donor_metadata = preflight_donor(donor)
    stock_metadata = verify_family_stock(stock, MODEL)
    kernel_metadata = json.loads((kernel / "input.json").read_text())
    if (kernel_metadata.get("model") != MODEL or
            kernel_metadata.get("device") != DEVICE or
            kernel_metadata.get("kind") != "experimental-oneui9-s10-netlink-xperm-kernel"):
        raise ValueError("Model-specific G975F kernel must have verified build metadata")
    for name, spec in kernel_metadata.get("images", {}).items():
        source = kernel / name
        if name not in ("boot.img", "dtb.img", "dtbo.img") or digest(source) != spec["sha256"]:
            raise ValueError("Missing or modified model-specific kernel image: " + name)
    with tempfile.TemporaryDirectory(prefix="astropart-s26u-", dir=output.parent) as temp:
        work = Path(temp)
        subprocess.run(["cp", "-a", str(donor / "tree"), str(work / "tree")], check=True)
        subprocess.run(["cp", "-a", str(stock / "vendor"), str(work / "vendor")], check=True)
        system = work / "tree/system"
        inventory_before = inventory_packages(system)
        if any(not inventory_before[role] for role in ("gms", "gsf", "play_store", "modern_camera")):
            raise ValueError("Donor is missing Google services or its modern Samsung Camera; no silent fallback")
        modern_camera_sha = inventory_before["camera_apk_sha256"]
        identity = update_model_identity(system)
        stock_system = stock / "tree/system"
        features = apply_features(system / "etc/floating_feature.xml",
                                  stock_system / "etc/floating_feature.xml", MODEL)
        support_libs = inject_stock_camera_support(system, stock_system)
        # The modern Camera APK MUST remain the S26 Ultra signed version.
        if digest(system / CAMERA_APK) != modern_camera_sha:
            raise ValueError("Modern Camera APK unexpectedly changed during adaptation")
        if not (work / "vendor/etc/vintf/manifest.xml").is_file():
            raise ValueError("G975F vendor VINTF manifest is missing")
        if display_bundle:
            # Require an independently compiled, checksum-verified model bundle.
            bundle = json.loads((display_bundle / "manifest.json").read_text())
            if MODEL not in bundle.get("models", {}):
                raise ValueError("No G975F display profile in display defaults bundle")
            from s10_display_defaults import FILES
            for name, relative in FILES.items():
                source = display_bundle / name
                if digest(source) != bundle["outputs"][name]:
                    raise ValueError("Tampered display bundle: " + name)
                dest = system / relative
                if dest.exists():
                    raise ValueError("Display default collision: " + relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                reference = (system / "framework/framework.jar" if relative.startswith("framework/") else
                             system / "etc/init" / "init.rc" if relative.startswith("etc/init/") else
                             system / "etc/floating_feature.xml")
                if not reference.is_file():
                    raise ValueError("Missing SELinux context reference for display file")
                os.chown(dest, 0, 0)
                os.chmod(dest, 0o644)
                os.setxattr(dest, "security.selinux", os.getxattr(reference, "security.selinux"))
        else:
            # Do not represent geometry alone as a finished overlay installation.
            raise ValueError("The compiled S10+ display-defaults bundle is required")
        check = inventory_packages(system)
        if check["modern_camera"] != inventory_before["modern_camera"]:
            raise ValueError("The Camera package path was modified")
        if any(not check[role] for role in ("gms", "gsf", "play_store")):
            raise ValueError("GMS packages disappeared while adapting")
        report = {
            "schema": 1, "kind": "experimental-astropart-s26u-g975f-merged-tree",
            "model": MODEL, "device": DEVICE,
            "donor_build": donor_metadata["build"], "stock_build": MODELS[MODEL]["build"],
            "kernel": kernel_metadata, "identity": identity,
            "camera_source": "S26 Ultra donor", "camera_sha256": modern_camera_sha,
            "camera_support_libraries": support_libs,
            "s10_floating_features": features,
            "packages_present": check,
            "debloated": False,
            "physical_boot_tested": False,
            "gms_functional": False,
            "camera_functional": False,
            "galaxy_ai_functional": False,
            "vendor_policy_reconciled": False,
            "ready_for_installation": False,
            "repartition": False,
        }
        # Do not claim that Android 17's SELinux and old vendor VINTF are
        # compatible until their actual generated namespaces are compiled.
        (work / "input.json").write_text(json.dumps(report, indent=2) + "\n")
        work.rename(output)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("donor", "stock", "kernel", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--display-bundle", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare(args.donor, args.stock, args.kernel, args.output, args.display_bundle)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
