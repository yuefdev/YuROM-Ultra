#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the verified Google Photos split set and the Camera-only gallery adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


PHOTOS_APKS = {
    "base.apk": "99cb38e442eec74e8ac56ae4a7d7a233cd83280d7b2036eaa62fde571d06cf3c",
    "split_config.arm64_v8a.apk": "26d03baf3086f2f02185e3ff38f03f55c90d3c4ad35f0874b02950626a10962a",
    "split_config.tr.apk": "2f0bf39e23b70c856a8aa365e9c1ee00bacb6ec6d790e8343d08964f4fd8eb88",
    "split_config.xxhdpi.apk": "b470bdeca0102504069481a58ba43bc7d28702ccd5eb299d0de33457b5549fa4",
}
PHOTOS_SIGNER = "5aad2bee6db95d17e05a08d7d1e64c10a1511879154483916b6ae6c7fd9cb0c6"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def integrate_google_photos(system, photos_input, bridge_input):
    checkout = Path(__file__).resolve().parent.parent
    photos = json.loads((photos_input / "input.json").read_text())
    bridge = json.loads((bridge_input / "input.json").read_text())
    if (photos.get("package") != "com.google.android.apps.photos" or photos.get("version_code") != 52514897
            or photos.get("signer_sha256") != PHOTOS_SIGNER or set(photos["apk_files"]) != set(PHOTOS_APKS)):
        raise RuntimeError("Unexpected Google Photos input")
    for name, expected in PHOTOS_APKS.items():
        if photos["apk_files"][name]["sha256"] != expected or digest(photos_input / name) != expected:
            raise RuntimeError("Google-signed Photos APK differs: " + name)
    resources = checkout / "target/beyond1lte/oneui9/gallery-bridge"
    if (bridge.get("package") != "com.sec.android.gallery3d" or bridge.get("version_code") != 2
            or bridge.get("signature_and_alignment_verified") is not True
            or digest(bridge_input / "gallery-bridge.apk") != bridge["apk_sha256"]
            or digest(checkout / "scripts/android/GalleryBridge.java") != bridge["java_sha256"]
            or digest(resources / "AndroidManifest.xml") != bridge["manifest_sha256"]):
        raise RuntimeError("Gallery adapter input is stale or unverified")
    permissions = "etc/default-permissions/default-permissions-artisan-gallery.xml"
    if any((system / name).exists() for name in ("app/GooglePhotos", "app/CameraGalleryBridge", permissions)):
        raise RuntimeError("Existing gallery integration must not be overwritten")
    files = {}

    def write(relative, data):
        destination = system / relative
        missing = []
        parent = destination.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o755)
            os.chown(directory, 0, 0)
            os.setxattr(directory, "security.selinux", b"u:object_r:system_file:s0\0")
        with destination.open("xb") as stream:
            stream.write(data)
        os.chown(destination, 0, 0)
        destination.chmod(0o644)
        os.setxattr(destination, "security.selinux", b"u:object_r:system_file:s0\0")
        files[relative] = digest(destination)

    for name in PHOTOS_APKS:
        write("app/GooglePhotos/" + name, (photos_input / name).read_bytes())
    if photos["extract_native_libs"]:
        for name in PHOTOS_APKS:
            with zipfile.ZipFile(photos_input / name) as archive:
                for entry in archive.namelist():
                    if not entry.startswith("lib/arm64-v8a/") or not entry.endswith(".so"):
                        continue
                    if len(Path(entry).parts) != 3:
                        raise RuntimeError("Unexpected Photos native library path")
                    data = archive.read(entry)
                    if data[:6] != b"\x7fELF\x02\x01" or data[18:20] != b"\xb7\x00":
                        raise RuntimeError("Expected an ARM64 Photos native library")
                    write("app/GooglePhotos/lib/arm64/" + Path(entry).name, data)
    write("app/CameraGalleryBridge/CameraGalleryBridge.apk", (bridge_input / "gallery-bridge.apk").read_bytes())
    write(permissions, (resources / "default-permissions.xml").read_bytes())
    return {"package": photos["package"], "version_name": photos["version_name"], "version_code": 52514897,
            "signer_sha256": PHOTOS_SIGNER, "google_apks_unmodified": True, "samsung_apk_unmodified": True,
            "installation_lifecycle": "normal split system application; existing data-app updates and user data retained",
            "gallery_adapter": bridge, "photos_app_data_not_modified_by_integration": True,
            "backup_setting_overrides": False,
            "files": files, "device_acceptance": "pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--photos-input", type=Path, required=True)
    parser.add_argument("--bridge-input", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if os.geteuid() != 0 or not args.records.is_dir() or args.records.resolve().is_relative_to(checkout):
        parser.error("Linux root and an existing external records directory are required")
    report = args.records / "google-photos-integration.json"
    if report.exists():
        parser.error("Completed gallery records must not be overwritten")
    result = integrate_google_photos(args.system, args.photos_input, args.bridge_input)
    with report.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
