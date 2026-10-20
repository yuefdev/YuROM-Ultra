#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pack experimental S10 images and verify capacity, files and Android labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from s10_models import MODELS, layout_for


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--reuse-vendor-sha256", help="Reuse an exact existing vendor image while rebuilding and verifying system")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if os.geteuid() != 0 or not args.records.is_dir() or args.records.resolve().is_relative_to(checkout):
        parser.error("Linux root and an existing external records directory are required")
    manifest = json.loads((args.candidate / "input.json").read_text())
    if manifest.get("kind") != "experimental-oneui9-s10-merged-system-with-hwc1-vendor" or manifest.get("model") not in MODELS:
        parser.error("The original-layout experimental S10 candidate is required")
    model = manifest["model"]
    if manifest.get("stock_build") != MODELS[model]["build"] or (model != "SM-G973F" and manifest.get("kernel", {}).get("model") != model):
        parser.error("The candidate must use its model's registered stock vendor and kernel")
    if any((args.candidate / name).exists() for name in ("system.img", "images.json")) or ((args.candidate / "vendor.img").exists() and not args.reuse_vendor_sha256):
        parser.error("Completed or incomplete candidate images must not be overwritten")
    layout = layout_for(model)
    system_image = args.candidate / "system.img"
    vendor_image = args.candidate / "vendor.img"
    if args.reuse_vendor_sha256 and (not re.fullmatch(r"[0-9a-f]{64}", args.reuse_vendor_sha256)
            or not vendor_image.is_file() or vendor_image.stat().st_size != layout["partitions"]["vendor"]["bytes"]
            or digest(vendor_image) != args.reuse_vendor_sha256):
        parser.error("The existing model vendor image must match its complete verified size and SHA256")
    with (args.records / "system-image.log").open("xb") as stream:
        subprocess.run(["mkfs.erofs", "-z", "lz4", "-C", "4096", "-E", "legacy-compress", "-b", "4096",
                        str(system_image), str(args.candidate / "tree")], stdout=stream, stderr=subprocess.STDOUT, check=True)
    if system_image.stat().st_size > layout["partitions"]["system"]["bytes"]:
        raise RuntimeError("System image exceeds the measured stock partition")
    if not args.reuse_vendor_sha256:
        with vendor_image.open("xb") as stream:
            stream.truncate(layout["partitions"]["vendor"]["bytes"])
        with (args.records / "vendor-image.log").open("xb") as stream:
            subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-I", "256", "-m", "0",
                            "-O", "^64bit,^metadata_csum,^orphan_file", "-L", "vendor", "-d", str(args.candidate / "vendor"),
                            str(vendor_image)], stdout=stream, stderr=subprocess.STDOUT, check=True)
    with (args.records / "image-integrity.log").open("xb") as stream:
        subprocess.run(["fsck.erofs", "--extract", str(system_image)], stdout=stream, stderr=subprocess.STDOUT, check=True)
        subprocess.run(["e2fsck", "-fn", str(vendor_image)], stdout=stream, stderr=subprocess.STDOUT, check=True)
    comparisons = []
    with tempfile.TemporaryDirectory(prefix="s10-image-check-") as temporary:
        root = Path(temporary)
        for name, kind, image, expected_root, paths in (
            ("system", "erofs", system_image, args.candidate / "tree", (
                 "system/build.prop", "system/bin/init", "system/bin/app_process32", "system/etc/vintf/compatibility_matrix.3.xml",
                "system/etc/vintf/compatibility_matrix.6.xml", "system/etc/vintf/compatibility_matrix.device.xml",
                 "system/etc/vintf/manifest/legacy-vndk31.xml", "system/etc/selinux/plat_sepolicy.cil",
                 "system/lib64/libui.so", "system/lib/libui.so", "system/etc/init/xgsi-usb.rc",
                  "system/etc/init/aconfigd.rc", "system/etc/selinux/plat_file_contexts",
                  "system/etc/floating_feature.xml", "system/etc/init/hw/init.usb.rc", "system/etc/ueventd.rc")),
            ("vendor", "ext4", vendor_image, args.candidate / "vendor", (
                "build.prop", "etc/selinux/precompiled_sepolicy", "etc/selinux/precompiled_sepolicy.plat_sepolicy_and_mapping.sha256",
                "etc/vintf/manifest.xml", "etc/fstab.exynos9820", "bin/hw/android.hardware.audio.service"))):
            mount = root / name
            mount.mkdir()
            subprocess.run(["mount", "-t", kind, "-o", "loop,ro,noload" if kind == "ext4" else "loop,ro",
                            str(image), str(mount)], check=True)
            try:
                if name == "system" and (expected_root / "adb_keys").is_file():
                    paths += ("adb_keys",)
                if name == "system":
                    for integration in ("samsung_camera_integration", "google_photos_integration", "s10_media_compatibility", "s10_personal_data_compatibility", "telemetry", "s10_display_defaults", "yurom_branding"):
                        if manifest.get(integration):
                            paths += tuple("system/" + relative for relative in manifest[integration]["files"])
                    if manifest.get("artisan_control"):
                        paths += ("system/framework/framework.jar", "system/framework/services.jar",
                                  "system/priv-app/SecSettings/SecSettings.apk",
                                  "system/system_ext/priv-app/SystemUI/SystemUI.apk",
                                  "system/priv-app/TouchWizHome_2017/TouchWizHome_2017.apk",
                                  "system/framework/artisan-control-broker.jar", "system/etc/init/artisan-control.rc",
                                  "system/bin/vold")
                    if manifest.get("s10_hdmi_audio_compatibility"):
                        paths += tuple("system/" + relative for relative in manifest["s10_hdmi_audio_compatibility"]["policy_files"])
                if name == "vendor":
                    for integration in ("s10_native_zygote_compatibility", "s10_legacy_scheduler_compatibility", "s10_boot_performance"):
                        if manifest.get(integration):
                            paths += tuple(manifest[integration]["files"])
                    if manifest.get("s10_hdmi_audio_compatibility"):
                        paths += ("lib/hw/audio.primary.exynos9820.so",)
                for relative in paths:
                    source = expected_root / relative
                    if not source.is_file():
                        raise RuntimeError(f"Required candidate file is missing: {name}/{relative}")
                    packed = mount / relative
                    if digest(source) != digest(packed):
                        raise RuntimeError(f"Packed file differs from the candidate: {name}/{relative}")
                    before, after = source.stat(), packed.stat()
                    if (before.st_uid, before.st_gid, before.st_mode & 0o7777) != (after.st_uid, after.st_gid, after.st_mode & 0o7777):
                        raise RuntimeError(f"Android owner/mode changed while packing: {name}/{relative}")
                    if os.getxattr(source, "security.selinux") != os.getxattr(packed, "security.selinux"):
                        raise RuntimeError(f"SELinux label changed while packing: {name}/{relative}")
                    comparisons.append(name + "/" + relative)
            finally:
                subprocess.run(["umount", str(mount)], check=True)
    report = {"capacity_checks": "passed", "erofs_full_decompression": "passed", "ext4_read_only_fsck": "passed",
              "verified_contents_owner_mode_labels": comparisons, "device_boot_tested": False}
    with (args.records / "image-verification.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    result = {"schema": 1, "kind": "experimental-oneui9-s10-images", "model": model, "images": {}, "ready_for_installation": False}
    for name, path in (("system", system_image), ("vendor", vendor_image)):
        result["images"][path.name] = {"size": path.stat().st_size, "sha256": digest(path),
                                      "partition_capacity": layout["partitions"][name]["bytes"]}
    with (args.candidate / "images.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
