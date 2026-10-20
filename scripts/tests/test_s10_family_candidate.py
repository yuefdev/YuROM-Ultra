#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify hardware preservation, model DTBO, native bundle and FBE contracts before packing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_s10_family_candidate import signature
from s10_models import MODELS, ROOT, digest, layout_for


def main(args):
    manifest = json.loads((args.candidate / "input.json").read_text())
    model = manifest["model"]
    assert model in MODELS and manifest["stock_build"] == MODELS[model]["build"]
    system, vendor = args.candidate / "tree/system", args.candidate / "vendor"
    assert not (args.candidate / "tree/adb_keys").exists() and not (system / "etc/security/adb_keys").exists()
    assert digest(system / "bin/vold") == "1856ffbd5dfd3922c0987fced54031e40ebad03bc84c6b0f540995946dbc7009"
    bundle = json.loads((args.bundle / "manifest.json").read_text())
    for label, spec in bundle["inputs"].items():
        target = system / spec["path"]
        assert digest(target) == bundle["outputs"][label + target.suffix]
    assert digest(system / "framework/artisan-control-broker.jar") == bundle["outputs"]["ArtisanControlBroker.jar"]
    if manifest.get("s10_personal_data_compatibility"):
        from s10_personal_data import FEATURE
        features = {node.tag: node.text for node in ET.parse(system / "etc/floating_feature.xml").getroot()}
        assert features[FEATURE] == "FALSE"
        for name, expected in manifest["s10_personal_data_compatibility"]["files"].items():
            assert digest(system / name) == expected
    if manifest.get("telemetry"):
        telemetry = json.loads((system / "etc/artisan-telemetry.json").read_text())
        assert telemetry["schema"] == 1 and telemetry["build"] == manifest["distribution"]["version"]
        assert telemetry["endpoint"] == manifest["telemetry"].get("endpoint", "")
        assert not (args.candidate / "tree/data/system/artisan-control/telemetry.json").exists()
        assert manifest["telemetry"]["opt_in_required"]
    if manifest.get("s10_display_defaults"):
        from s10_display_defaults import FILES
        display = manifest["s10_display_defaults"]
        assert model == display["model"]
        profile = display["models"][model]
        assert display["default_native_mode"] == [1080, 2280, 60.000004]
        assert display["camera_inset_portrait_dp"] == profile["portrait_indicator_padding_dp"] and display["preserves_subsequent_user_preferences"]
        assert display["default_density"] == profile["default_density"]
        assert set(display["files"]) == set(FILES.values())
        for name, relative in FILES.items():
            assert digest(system / relative) == display["outputs"][name]
    profile = json.loads((vendor / "etc/s10-performance-control.json").read_text())
    assert profile["model"] == model and profile["boot_sha256"] == digest(args.boot) == manifest["s10_boot_performance"]["kernel_sha256"]
    assert args.boot.stat().st_size == layout_for(model)["partitions"]["boot"]["bytes"]
    for name, spec in manifest["s10_boot_performance"]["files"].items():
        assert digest(vendor / name) == spec["sha256"]
    untouched = 0
    if model != "SM-G973F":
        exceptions = set(manifest["model_vendor_patch_files"])
        for path in (args.stock / "vendor").rglob("*"):
            relative = path.relative_to(args.stock / "vendor")
            if str(relative) in exceptions:
                continue
            packed = vendor / relative
            assert signature(path) == signature(packed), "Model hardware input changed: " + str(relative)
            before, after = path.lstat(), packed.lstat()
            assert (before.st_uid, before.st_gid, before.st_mode) == (after.st_uid, after.st_gid, after.st_mode)
            if not path.is_symlink():
                assert os.getxattr(path, "security.selinux") == os.getxattr(packed, "security.selinux")
            untouched += 1
        assert digest(system / "priv-app/SamsungCamera/SamsungCamera.apk") == digest(args.stock / "tree/system/priv-app/SamsungCamera/SamsungCamera.apk")
        features = {node.tag: node.text for node in ET.parse(system / "etc/floating_feature.xml").getroot()}
        assert features["SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE"] == "60"
        assert features["SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE"] == "0"
        assert features["SEC_FLOATING_FEATURE_BIOAUTH_CONFIG_FINGERPRINT_FEATURES"] == ("capacitive_side" if model == "SM-G970F" else "ultrasonic_display_phone")
        kernel = json.loads((args.kernel / "input.json").read_text())
        assert kernel["model"] == model
        config = (args.kernel / "obj/.config").read_text().splitlines()
        for required in (("CONFIG_SENSORS_ET5XX=y", "# CONFIG_SENSORS_QBT2000 is not set", "CONFIG_EXYNOS_DECON_LCD_S6E3FA7=y") if model == "SM-G970F" else ("CONFIG_CAMERA_CIS_4HA_OBJ=y", "CONFIG_CAMERA_BSS_V02=y")):
            assert required in config
        data = (args.kernel / "dtbo.img").read_bytes()
        magic, size, header_size, entry_size, count, offset, page, version = struct.unpack_from(">8I", data)
        assert magic == 0xd7b7ab1e and header_size == 32 and entry_size == 32 and size == len(data)
        source = ROOT / "out/kernels/s10-family-source-v11/build/dtconfigs" / (MODELS[model]["device"] + ".cfg")
        expected = []
        for line in source.read_text().splitlines():
            if "custom0=" in line:
                expected.append([int(line.split("=")[1], 0)])
            if "custom1=" in line:
                expected[-1].append(int(line.split("=")[1], 0))
        assert count == len(expected)
        for i, revisions in enumerate(expected):
            entry = struct.unpack_from(">8I", data, offset + i * entry_size)
            assert list(entry[4:6]) == revisions
            assert data[entry[1]:entry[1] + 4] == b"\xd0\x0d\xfe\xed"
        with tempfile.TemporaryDirectory(prefix="s10-fbe-check-") as temporary:
            archive = subprocess.run(["gzip", "-dc", str(args.kernel / "ramdisk.cpio.gz")], check=True, capture_output=True).stdout
            subprocess.run(["cpio", "-i", "--quiet", "fstab.exynos9820"], cwd=temporary, input=archive, check=True)
            fstab = (Path(temporary) / "fstab.exynos9820").read_text()
        userdata = next(line for line in fstab.splitlines() if line.split()[1:2] == ["/data"])
        assert "fileencryption=aes-256-xts:aes-256-cts:v2" in userdata and "fileencryption=ice" not in userdata
        cache = next(line for line in fstab.splitlines() if line.split()[1:2] == ["/cache"])
        assert "first_stage_mount" in cache
    print(json.dumps({"model": model, "untouched_model_vendor_entries": untouched,
                      "native_bundle": "passed", "boot_profile": "passed", "model_dtbo_fbe": "passed" if model != "SM-G973F" else "retained working reference"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "stock", "kernel", "boot", "bundle"):
        parser.add_argument("--" + name, type=Path, required=True)
    main(parser.parse_args())
