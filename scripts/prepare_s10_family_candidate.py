#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive model ROM trees from verified stock vendor and the complete native V25 port."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from prepare_oneui9_s10_candidate import set_property
from s10_boot_performance import configure_boot_performance
from s10_models import MODELS, ROOT, digest, verify_family_stock

BASE_SYSTEM = "a8990177b2d5c578561326b71b53252797265262503f8058848eddd437dfacbf"
BASE_VENDOR = "c21d814cd17eadce60085d4381cb8a644d86718749dbca5ad76dcdc69c58772b"


def signature(path):
    if path.is_symlink():
        return ("link", os.readlink(path))
    if path.is_file():
        return ("file", digest(path))
    if path.is_dir():
        return ("directory",)
    return None


def vendor_delta(original, baseline, model_vendor):
    """Only transfer a shared patch when its complete original model input matches."""
    rows = []
    paths = {p.relative_to(root) for root in (original, baseline) for p in root.rglob("*")}
    for relative in sorted(paths):
        before, after = signature(original / relative), signature(baseline / relative)
        if before == after:
            continue
        if signature(model_vendor / relative) != before or after is None:
            raise ValueError("Shared vendor compatibility patch conflicts with model hardware: " + str(relative))
        rows.append(str(relative))
    if len(rows) != 40:
        raise ValueError("The registered V25 vendor compatibility inventory changed")
    return rows


def apply_features(target, stock, model):
    before = target.read_text()
    reference = stock.read_text()
    source = {node.tag: node.text or "" for node in ET.fromstring(reference)}
    selected = {key: value for key, value in source.items() if key.startswith(("SEC_FLOATING_FEATURE_CAMERA_", "SEC_FLOATING_FEATURE_LCD_"))}
    for key in ("SEC_FLOATING_FEATURE_LOCKSCREEN_CONFIG_PUNCHHOLE_VI", "SEC_FLOATING_FEATURE_COMMON_CONFIG_EDGE"):
        if key in source:
            selected[key] = source[key]
    # Disable donor-only variable refresh/fullscreen AOD on the original 60 Hz panels.
    selected.update({"SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_FULLSCREEN": "0", "SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_BRIGHTNESS_ANIMATION": "0",
                     "SEC_FLOATING_FEATURE_BIOAUTH_CONFIG_FINGERPRINT_FEATURES": "capacitive_side" if model == "SM-G970F" else "ultrasonic_display_phone"})
    root = ET.fromstring(before)
    for node in list(root):
        if node.tag.startswith(("SEC_FLOATING_FEATURE_CAMERA_", "SEC_FLOATING_FEATURE_LCD_")) or node.tag in selected:
            root.remove(node)
    for key, value in selected.items():
        ET.SubElement(root, key).text = value
    target.write_text(ET.tostring(root, encoding="unicode") + "\n")
    return selected


def camera_preflight(system, stock, native_manifest):
    old_apk = system / "priv-app/SamsungCamera/SamsungCamera.apk"
    model_apk = stock / "priv-app/SamsungCamera/SamsungCamera.apk"
    with zipfile.ZipFile(old_apk) as old, zipfile.ZipFile(model_apk) as model:
        if old.namelist() != model.namelist():
            raise ValueError("Camera APK member inventory differs")
        for name in old.namelist():
            if not name.startswith(("META-INF/", "SEC-INF/")) and old.read(name) != model.read(name):
                raise ValueError("The model Camera code/resources require a separate adapter: " + name)
        for name, expected in native_manifest["files"].items():
            if not name.startswith("lib/"):
                continue
            leaf = Path(name).name
            patch = native_manifest["elf_changes"].get("libion.so" if leaf == "libs10.so" else leaf)
            source_name = "libion.so" if leaf == "libs10.so" else leaf
            entry = "lib/arm64-v8a/" + source_name
            if entry in model.namelist():
                checksum = hashlib.sha256(model.read(entry)).hexdigest()
            else:
                source = stock / "lib64" / source_name
                if not source.is_file():
                    source = stock.parent.parent / "vendor/lib64" / source_name
                if not source.is_file():
                    raise ValueError("Missing model Camera dependency: " + source_name)
                checksum = digest(source)
            if checksum != (patch["original_sha256"] if patch else expected):
                raise ValueError("The app-private Camera native adapter does not match model input: " + source_name)
            if digest(system / "priv-app/SamsungCamera" / name) != expected:
                raise ValueError("The baseline Camera native library changed: " + name)


def prepare(args):
    resume = args.resume_copy and args.output.is_dir() and {p.name for p in args.output.iterdir()} == {"tree"}
    if (os.geteuid() != 0 or (args.output.exists() and not resume) or not args.output.parent.is_dir()
            or not args.records.is_dir() or args.records.resolve().is_relative_to(ROOT)):
        raise ValueError("Linux root, new candidate output and existing external records are required")
    metadata = json.loads((args.baseline / "input.json").read_text())
    if metadata.get("model") != "SM-G973F" or digest(args.baseline / "system.img") != BASE_SYSTEM or digest(args.baseline / "vendor.img") != BASE_VENDOR:
        raise ValueError("The complete original-layout V25 baseline is required")
    kernel = json.loads((args.kernel / "input.json").read_text())
    if args.model == "SM-G973F":
        stock = None
        if digest(args.boot) != metadata["s10_boot_performance"]["kernel_sha256"]:
            raise ValueError("The working G973F full boot pin must be retained")
        patches = []
    else:
        stock = verify_family_stock(args.stock, args.model)
        if kernel.get("model") != args.model or kernel.get("device") != MODELS[args.model]["device"]:
            raise ValueError("A separately built kernel and DTBO for this model are required")
        for name, spec in kernel["images"].items():
            if digest(args.kernel / name) != spec["sha256"]:
                raise ValueError("The model kernel image changed: " + name)
        if args.boot.resolve() != (args.kernel / "boot.img").resolve():
            raise ValueError("Use the model's own full boot image")
        patches = vendor_delta(args.reference_stock / "vendor", args.baseline / "vendor", args.stock / "vendor")
        native = json.loads((args.camera_native / "input.json").read_text())
        camera_preflight(args.baseline / "tree/system", args.stock / "tree/system", native)
    bundle = json.loads((args.bundle / "manifest.json").read_text())
    if args.model == "SM-G970F" and bundle.get("model_adaptation", {}).get("model") != args.model:
        raise ValueError("The S10e side-fingerprint native adapter is required")
    if args.model != "SM-G970F" and bundle.get("model_adaptation"):
        raise ValueError("Side-sensor firmware cannot be installed on an in-display sensor model")
    for name, expected in bundle["outputs"].items():
        if Path(name).name != name or digest(args.bundle / name) != expected:
            raise ValueError("Artisan bundle hash mismatch")
    args.output.mkdir(exist_ok=resume)
    for name, source in (("tree", args.baseline / "tree"), ("vendor", (args.stock / "vendor") if stock else args.baseline / "vendor")):
        destination = args.output / name
        destination.mkdir(exist_ok=resume)
        subprocess.run(["cp", "-a", "--reflink=auto", str(source) + "/.", str(destination)], check=True)
    system, vendor = args.output / "tree/system", args.output / "vendor"
    if stock:
        for name in patches:
            source, target = args.baseline / "vendor" / name, vendor / name
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copystat(source, target)
                os.chown(target, source.stat().st_uid, source.stat().st_gid)
            else:
                subprocess.run(["cp", "-a", str(source), str(target)], check=True)
        for name in ("etc/init/02-s10-performance.rc", "etc/s10-performance-profile.sh"):
            (vendor / name).unlink()
        metadata["s10_boot_performance"] = configure_boot_performance(vendor, model=args.model, kernel=kernel)
        model_system = args.stock / "tree/system"
        for partition, file in (("system", system / "build.prop"), ("system_ext", system / "system_ext/etc/build.prop"), ("product", system / "product/etc/build.prop")):
            for field, value, expected in (("model", args.model, "SM-G973F"), ("device", MODELS[args.model]["device"].removesuffix("lte"), "beyond1"),
                                           ("name", MODELS[args.model]["device"] + "xx", "beyond1ltexx")):
                set_property(file, "ro.product." + partition + "." + field, value, expected)
        metadata["model_hardware_features"] = apply_features(system / "etc/floating_feature.xml", model_system / "etc/floating_feature.xml", args.model)
        for name in metadata["copied_stock_inputs"]:
            source, target = model_system / name, system / name
            target.write_bytes(source.read_bytes())
            metadata["copied_stock_inputs"][name] = digest(target)
        # Keep the original model APK signed and use the preflight-proven common native adapter.
        camera = system / "priv-app/SamsungCamera/SamsungCamera.apk"
        camera.write_bytes((model_system / "priv-app/SamsungCamera/SamsungCamera.apk").read_bytes())
        shutil.rmtree(system / "cameradata")
        subprocess.run(["cp", "-a", str(model_system / "cameradata"), str(system / "cameradata")], check=True)
        metadata["samsung_camera_integration"].update({"source_build": stock["build"], "apk_sha256": digest(camera)})
        metadata["samsung_camera_integration"]["camera_features"] = {key: value for key, value in metadata["model_hardware_features"].items() if key.startswith("SEC_FLOATING_FEATURE_CAMERA_")}
        metadata["samsung_camera_integration"]["files"] = {str(p.relative_to(system)): digest(p) for directory in (system / "cameradata", system / "priv-app/SamsungCamera") for p in directory.rglob("*") if p.is_file()}
        metadata["samsung_camera_integration"]["files"]["etc/floating_feature.xml"] = digest(system / "etc/floating_feature.xml")
        metadata["model_vendor_patch_files"] = patches
        metadata["stock_build"] = stock["build"]
        metadata["stock_input_archive_sha256"] = stock["archive_sha256"]
        metadata["kernel"] = kernel
    else:
        for name in ("etc/init/02-s10-performance.rc", "etc/s10-performance-profile.sh"):
            (vendor / name).unlink()
        metadata["s10_boot_performance"] = configure_boot_performance(vendor)
    for label, spec in bundle["inputs"].items():
        target = system / spec["path"]
        if digest(target) != metadata["artisan_control"]["outputs"][label + target.suffix]:
            raise ValueError("The baseline native Artisan target changed: " + label)
        target.write_bytes((args.bundle / (label + target.suffix)).read_bytes())
    (system / "framework/artisan-control-broker.jar").write_bytes((args.bundle / "ArtisanControlBroker.jar").read_bytes())
    metadata["artisan_control"].update({"outputs": bundle["outputs"], "features": bundle["features"]})
    metadata["s10_settings_branding"]["settings_sha256"] = bundle["outputs"]["settings.apk"]
    if args.pde_bundle:
        from s10_personal_data import configure as configure_pde
        metadata["s10_personal_data_compatibility"] = configure_pde(system, args.pde_bundle)
        metadata["samsung_camera_integration"]["files"]["etc/floating_feature.xml"] = digest(system / "etc/floating_feature.xml")
    from s10_telemetry import configure as configure_telemetry
    metadata["telemetry"] = configure_telemetry(system, args.version, args.telemetry_endpoint)
    from s10_display_defaults import configure as configure_display_defaults
    display_defaults = configure_display_defaults(ROOT, system, args.model)
    if display_defaults is not None:
        metadata["s10_display_defaults"] = display_defaults
    if "brand_derivation" in bundle:
        from s10_yurom_branding import configure as configure_yurom_branding
        metadata["yurom_branding"] = configure_yurom_branding(system, args.model, ROOT / "out/host-tools/yurom-settings-signature-v35.apk")
        metadata["s10_settings_branding"]["apk_sha256"] = metadata["yurom_branding"]["signature_sha256"]
        metadata["s10_settings_branding"]["settings_sha256"] = bundle["outputs"]["settings.apk"]
    metadata.update({"model": args.model, "parent_candidate": args.baseline.name, "layout": MODELS[args.model]["device"],
                     "adaptive_performance_control": {"surface": "native-settings", "local_learning": True, "device_tested": False},
                     "device_boot_tested": False, "ready_for_installation": False, "repartition": False})
    metadata["distribution"].update({"supported_model": args.model, "version": args.version, "final_zip_device_install_tested": False})
    (args.output / "input.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (args.records / "candidate-preparation.json").write_text(json.dumps({"model": args.model, "shared_vendor_patches": patches, "kernel": kernel["images"],
                                                                       "device_writes": False, "physical_acceptance": "pending"}, indent=2) + "\n")
    print("Prepared native " + args.version + " candidate: " + args.model)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--version", default="v28-test")
    parser.add_argument("--telemetry-endpoint", default=None)
    parser.add_argument("--pde-bundle", type=Path)
    parser.add_argument("--resume-copy", action="store_true", help="Resume only an interrupted initial tree copy before vendor creation")
    for name in ("baseline", "reference-stock", "stock", "kernel", "boot", "camera-native", "bundle", "output", "records"):
        parser.add_argument("--" + name, type=Path, required=True)
    prepare(parser.parse_args())
