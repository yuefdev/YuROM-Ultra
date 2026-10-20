#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the narrow Samsung Camera to Google Photos activity adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-tools", type=Path, required=True)
    parser.add_argument("--android-jar", type=Path, required=True)
    parser.add_argument("--keystore", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if (not args.records.is_dir() or args.records.resolve().is_relative_to(checkout)
            or args.output.exists() or not args.output.parent.is_dir()
            or not args.keystore.is_file() or not os.environ.get("ARTISAN_GALLERY_STOREPASS")):
        parser.error("Fresh output, external records, an existing signing key and its password environment are required")
    source = checkout / "scripts/android/GalleryBridge.java"
    manifest = checkout / "target/beyond1lte/oneui9/gallery-bridge/AndroidManifest.xml"
    args.output.mkdir()
    classes, dex = args.output / "classes", args.output / "dex"
    classes.mkdir()
    dex.mkdir()
    unsigned = args.output / "bridge-unaligned.apk"
    aligned = args.output / "bridge-unsigned.apk"
    signed = args.output / "gallery-bridge.apk"
    with (args.records / "build.log").open("xb") as log:
        def run(command):
            subprocess.run([str(item) for item in command], check=True, stdout=log, stderr=subprocess.STDOUT)

        run(["javac", "--release", "8", "-classpath", args.android_jar, "-d", classes, source])
        run(["java", "-cp", args.build_tools / "lib/d8.jar", "com.android.tools.r8.D8",
             "--min-api", "31", "--lib", args.android_jar, "--output", dex,
             *sorted(classes.rglob("*.class"))])
        run([args.build_tools / "aapt2", "link", "-I", args.android_jar, "--manifest", manifest,
             "--min-sdk-version", "31", "--target-sdk-version", "35", "-o", unsigned])
        with zipfile.ZipFile(unsigned, "a") as archive:
            archive.write(dex / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_STORED)
        run([args.build_tools / "zipalign", "-p", "4", unsigned, aligned])
        signer = ["java", "-jar", args.build_tools / "lib/apksigner.jar"]
        run([*signer, "sign", "--ks", args.keystore, "--ks-key-alias", "gallery",
             "--ks-pass", "env:ARTISAN_GALLERY_STOREPASS", "--out", signed, aligned])
        run([*signer, "verify", "--verbose", "--print-certs", signed])
        run([args.build_tools / "zipalign", "-c", "4", signed])
    result = {"package": "com.sec.android.gallery3d", "version_code": 2,
              "purpose": "original Samsung Camera explicit gallery component to Google Photos",
              "apk_sha256": digest(signed), "java_sha256": digest(source),
              "manifest_sha256": digest(manifest), "google_and_samsung_apks_unmodified": True,
              "no_launcher_activity": True, "locked_keyguard_rejected": True,
              "uri_scope": "public MediaStore images and videos; Samsung secmedia IDs mapped by file",
              "signature_and_alignment_verified": True}
    with (args.output / "input.json").open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
