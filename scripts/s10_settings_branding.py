#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the resource-only Software information signature without touching Settings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile

SETTINGS_SHA256 = "57792a331109cc889d8d2be0caa8d0d4e40ade53fc1e0c608e96c582b0d20b35"
PACKAGE = "com.artisanrom.s10.settings.signature"
ALLOWLIST_SHA256 = "3ba67d91f06e256c67228c2a85c6455f0a85bdac3f120b15fbd02cfd711b5bd5"
ALLOWLIST_ENTRY = ('    <allowed-system-preload package="' + PACKAGE + '"/>\n').encode()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preload_allowlist_patch(data):
    if hashlib.sha256(data).hexdigest() != ALLOWLIST_SHA256 or data.count(b"</config>") != 1:
        raise RuntimeError("Unexpected donor preload allowlist; retain its existing package contract")
    return data.replace(b"</config>", ALLOWLIST_ENTRY + b"</config>")


def settings_symbol_library(settings, output):
    """Expose OEM symbols as a dynamic import, not as the RRO's own 0x7f IDs.

    This compile-only library never leaves the temporary directory. The real
    Settings APK is read-only: only the symbol table's package-ID field changes.
    AAPT then emits a named dependency that AssetManager relocates to Settings.
    """
    with zipfile.ZipFile(settings) as source:
        table = bytearray(source.read("resources.arsc"))
        offset = struct.unpack_from("<H", table, 2)[0]
        packages = 0
        while offset < len(table):
            kind, header_size, size = struct.unpack_from("<HHI", table, offset)
            if size < header_size or offset + size > len(table):
                raise RuntimeError("Malformed donor resource table")
            if kind == 0x0200:
                if struct.unpack_from("<I", table, offset + 8)[0] != 0x7f:
                    raise RuntimeError("Unexpected donor resource package ID")
                struct.pack_into("<I", table, offset + 8, 0)
                packages += 1
            offset += size
        if packages != 1:
            raise RuntimeError("Expected exactly one Settings symbol package")
        with zipfile.ZipFile(output, "w") as library:
            library.writestr("AndroidManifest.xml", source.read("AndroidManifest.xml"))
            library.writestr("resources.arsc", table)


def build_overlay(checkout, settings, framework, output):
    if digest(settings) != SETTINGS_SHA256:
        raise RuntimeError("Settings differs from the pinned donor; review the preference contract first")
    sdk = checkout / "out/host-tools/android-sdk-36"
    tools = sdk / "build-tools/android-16"
    resources = checkout / "target/beyond1lte/oneui9/settings-branding"
    frames = [resources / "res/drawable-nodpi" / f"s10_blackhole_{index:02}.webp" for index in range(36)]
    required = [tools / name for name in ("aapt2", "zipalign", "lib/apksigner.jar")]
    if output.exists() or not output.parent.is_dir() or not all(p.is_file() for p in required):
        raise RuntimeError("A fresh output, existing parent and prepared Android 36 build tools are required")
    if not all(frame.is_file() for frame in frames):
        raise RuntimeError("The maintained Riftroam black-hole frames are required")

    def run(command):
        subprocess.run(list(map(str, command)), check=True)

    with tempfile.TemporaryDirectory(prefix="s10-settings-signature-") as temporary:
        temporary = Path(temporary)
        compiled = temporary / "resources.zip"
        unsigned = temporary / "unsigned.apk"
        aligned = temporary / "aligned.apk"
        signed = temporary / "signed.apk"
        symbols = temporary / "settings-symbols.apk"
        settings_symbol_library(settings, symbols)
        run([tools / "aapt2", "compile", "--dir", resources / "res", "-o", compiled])
        run([tools / "aapt2", "link", "--manifest", resources / "AndroidManifest.xml",
             "-I", framework, "-I", symbols, "--auto-add-overlay",
             "--no-resource-deduping", "--no-resource-removal", "-o", unsigned, compiled])
        run([tools / "zipalign", "-p", "4", unsigned, aligned])
        signer = ["java", "-jar", tools / "lib/apksigner.jar"]
        # Only the new, code-free RRO receives this key. The platform APK is untouched.
        run([*signer, "sign", "--key", checkout / "security/aosp_testkey.pk8",
             "--cert", checkout / "security/aosp_testkey.x509.pem", "--out", signed, aligned])
        run([*signer, "verify", signed])
        run([tools / "zipalign", "-c", "4", signed])
        with output.open("xb") as stream:
            stream.write(signed.read_bytes())
    if digest(settings) != SETTINGS_SHA256:
        raise RuntimeError("Settings changed during overlay construction")
    return {"package": PACKAGE, "settings_sha256": SETTINGS_SHA256,
            "apk_sha256": digest(output), "settings_apk_unmodified": True,
            "resource": "xml/sec_software_info_settings", "has_code": False,
            "background": {"source": "Riftroam black-hole shader", "frames": len(frames),
                           "width": 640, "height": 360, "frame_duration_ms": 56,
                           "decoded_bitmap_bytes": 640 * 360 * 4 * len(frames),
                           "shader_sha256": digest(resources / "blackhole.frag")},
            "preinstalled_legacy_system_overlay": True}


def configure_settings_branding(checkout, system):
    directory = system / "system_ext/overlay"
    reference = directory / "smartfaceservice_overlay.apk"
    if not reference.is_file() or {p.name for p in directory.iterdir()} != {reference.name}:
        raise RuntimeError("Review OverlayConfig when the pinned system_ext overlays change")
    allowlist = system / "etc/sysconfig/allowed-system-preload-apps.xml"
    allowlist_data = preload_allowlist_patch(allowlist.read_bytes())
    output = directory / "S10SettingsSignature.apk"
    metadata = build_overlay(checkout, system / "priv-app/SecSettings/SecSettings.apk",
                             system / "framework/framework-res.apk", output)
    os.chown(output, 0, 0)
    os.chmod(output, 0o644)
    os.setxattr(output, "security.selinux", os.getxattr(reference, "security.selinux"))
    config = directory / "config"
    config.mkdir(mode=0o755)
    os.chown(config, 0, 0)
    os.setxattr(config, "security.selinux", os.getxattr(directory, "security.selinux"))
    target = config / "config.xml"
    target.write_bytes((checkout / "target/beyond1lte/oneui9/settings-branding/OverlayConfig.xml").read_bytes())
    os.chown(target, 0, 0)
    os.chmod(target, 0o644)
    os.setxattr(target, "security.selinux", os.getxattr(reference, "security.selinux"))
    # In-place append preserves every original byte, copyright notice and xattr.
    allowlist.write_bytes(allowlist_data)
    metadata["preload_allowlist"] = {"original_sha256": ALLOWLIST_SHA256,
                                     "sha256": digest(allowlist), "added_package": PACKAGE}
    metadata["path"] = str(output.relative_to(system))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--framework", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = build_overlay(Path(__file__).resolve().parent.parent,
                             args.settings, args.framework, args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
