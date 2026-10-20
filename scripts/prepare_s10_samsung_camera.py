#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrate the original HWC1 Samsung Camera through its system-app lifecycle."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile


APK_SHA256 = "4a85de6ffa555da48c95ae1cbf262897f11aa72c058a32b41fd3f4955e0ad42a"
SIGNER_SHA256 = "34df0e7a9f1cf1892e45c056b4973cd81ccf148a4050d11aea4ac5a65f900a42"
CAMERA_PREFIX = "SEC_FLOATING_FEATURE_CAMERA_"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def align_dex_jar(source, destination):
    """Keep JAR payloads intact and permit direct mmap of every stored DEX."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "x") as packed:
        for entry in original.infolist():
            info = copy.copy(entry)
            if info.filename.endswith(".dex") and info.compress_type == zipfile.ZIP_STORED:
                offset = packed.fp.tell() + 30 + len(info.filename.encode("utf-8")) + len(info.extra)
                if offset % 4:
                    padding = (-offset - 6) % 4
                    info.extra += struct.pack("<HHH", 0xd935, 2 + padding, 4) + bytes(padding)
            packed.writestr(info, original.read(entry.filename))
    data = destination.read_bytes()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination) as packed:
        if original.namelist() != packed.namelist():
            raise RuntimeError("DEX alignment changed JAR entries")
        for entry in packed.infolist():
            if original.read(entry.filename) != packed.read(entry.filename):
                raise RuntimeError("DEX alignment changed a JAR payload")
            if entry.filename.endswith(".dex") and entry.compress_type == zipfile.ZIP_STORED:
                name_bytes, extra_bytes = struct.unpack_from("<HH", data, entry.header_offset + 26)
                if (entry.header_offset + 30 + name_bytes + extra_bytes) % 4:
                    raise RuntimeError("Stored DEX is not mmap-aligned")
    return {"payloads_unchanged": True, "stored_dex_alignment_bytes": 4,
            "original_envelope_sha256": digest(source), "jar_sha256": digest(destination)}


def features(text):
    root = ET.fromstring(text)
    result = {}
    for node in root:
        if node.tag in result:
            raise RuntimeError("Duplicate floating feature: " + node.tag)
        result[node.tag] = node.text or ""
    return result


def integrate_samsung_camera(system, stock_system):
    """Keep Samsung's APK unchanged and select the matching S10 camera inputs."""
    source = stock_system / "priv-app/SamsungCamera"
    destination = system / "priv-app/SamsungCamera"
    apk = source / "SamsungCamera.apk"
    if digest(apk) != APK_SHA256 or destination.exists():
        raise RuntimeError("Expected the original HWC1 Camera and an absent target app")
    signature = subprocess.run(["apksigner", "verify", "--print-certs", str(apk)],
                               check=True, capture_output=True, text=True).stdout
    if "Signer #1 certificate SHA-256 digest: " + SIGNER_SHA256 not in signature:
        raise RuntimeError("Unexpected Samsung Camera signer")
    for relative in ("framework/semextendedformat.jar", "framework/secimaging.jar",
                     "etc/permissions/privapp-permissions-com.sec.android.app.camera.xml"):
        if not (system / relative).is_file():
            raise RuntimeError("Required Camera framework input is absent: " + relative)
    required = ("libMyFilterPlugin.camera.samsung.so", "libagifencoder.quram.so",
                "libexifa.camera.samsung.so", "libjpega.camera.samsung.so",
                "libsecimaging_pdk.camera.samsung.so")
    public = set()
    for path in (system / "etc").glob("public.libraries*.txt"):
        public.update(line.split()[0] for line in path.read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith("#"))
    if any(not (system / "lib64" / name).is_file() or name not in public for name in required):
        raise RuntimeError("Required Samsung Camera native libraries are absent or private")
    data_source = stock_system / "cameradata"
    data_destination = system / "cameradata"
    if not (data_source / "camera-feature.xml").is_file() or any(data_destination.iterdir()):
        raise RuntimeError("Expected HWC1 camera data and an empty donor camera data directory")
    path = system / "etc/floating_feature.xml"
    before = path.read_text()
    stock_text = (stock_system / "etc/floating_feature.xml").read_text()
    before_features, stock_features = features(before), features(stock_text)
    stock_camera = {key: value for key, value in stock_features.items() if key.startswith(CAMERA_PREFIX)}
    if not stock_camera:
        raise RuntimeError("HWC1 camera floating features are absent")
    pattern = r"[ \t]*<SEC_FLOATING_FEATURE_CAMERA_[A-Z0-9_]+(?:>.*?</SEC_FLOATING_FEATURE_CAMERA_[A-Z0-9_]+>|\s*/>)[ \t]*\r?\n?"
    after = re.sub(pattern, "", before)
    additions = []
    for key in stock_camera:
        match = re.search(r"<" + key + r"(?:>.*?</" + key + r">|\s*/>)", stock_text)
        if match is None:
            raise RuntimeError("Unexpected HWC1 camera feature encoding: " + key)
        additions.append("    " + match[0] + "\n")
    after = after.replace("</SecFloatingFeatureSet>", "".join(additions) + "</SecFloatingFeatureSet>")
    after_features = features(after)
    if ({key: value for key, value in before_features.items() if not key.startswith(CAMERA_PREFIX)}
            != {key: value for key, value in after_features.items() if not key.startswith(CAMERA_PREFIX)}):
        raise RuntimeError("Camera integration changed an unrelated floating feature")
    if {key: value for key, value in after_features.items() if key.startswith(CAMERA_PREFIX)} != stock_camera:
        raise RuntimeError("Camera floating features do not match HWC1")
    # Preflight all inputs before adding files; cp retains Android ownership and xattrs.
    subprocess.run(["cp", "-a", str(source), str(destination)], check=True)
    subprocess.run(["cp", "-a", str(data_source) + "/.", str(data_destination)], check=True)
    path.write_text(after)
    changed = [path]
    changed += sorted(item for directory in (destination, data_destination)
                      for item in directory.rglob("*") if item.is_file())
    return {"source_build": "G973FXXSGHWC1", "version_name": "12.0.01.85",
            "package": "com.sec.android.app.camera", "apk_sha256": APK_SHA256,
            "signer_sha256": SIGNER_SHA256, "apk_unmodified": True,
            "installation_lifecycle": "original privileged system application",
            "camera_features": stock_camera, "unrelated_floating_features_unchanged": True,
            "files": {str(item.relative_to(system)): digest(item) for item in changed},
            "package_verification_unchanged": True, "policy_unchanged": True,
            "device_acceptance": "pending"}


def apply_camera_compatibility(system, version_build, activity_build):
    """Restore the two evidenced legacy APIs without altering the signed Camera."""
    changes = {}
    for name, build, original, previous, expected in (
            ("secimaging.jar", version_build,
             "c5e9998a37d68ff921ef119faa7709c76c8651f4d78c4c142508d6feb2fbd79b",
             "f5c318f530cfd7f3a72425b685cac69f8d2b47d05c98bbef70df3d3e0a1bb7e3",
             "b3635ab474515496c1bfc736a241091d2edfbba208d0219c7bdb6d276212742d"),
            ("framework.jar", activity_build,
             "91bb10a601564bef52a4b0a06443125a96584408679b106ebbc03fdf07b4b732",
             "67d4e85503770e095efa4c8192b4772251209abc0c6c1e5a4855622bcf1d7449",
             "94fbadff654584636bf62bf7faaf8b4dd9f671ed39fcf6d25b9cc4849b9e3f7b")):
        source_digest = digest(system / "framework" / name)
        if source_digest not in (original, previous) or digest(build / name) != expected:
            raise RuntimeError("Unexpected Camera compatibility input: " + name)
        metadata = json.loads((build / "input.json").read_text())
        if metadata["original_jar_sha256"] != original or metadata["jar_sha256"] != expected:
            raise RuntimeError("Camera compatibility provenance differs: " + name)
        changes["framework/" + name] = {"original_sha256": source_digest, "sha256": expected,
                                         "verification": metadata}
    for relative, metadata in changes.items():
        name = Path(relative).name
        build = version_build if name == "secimaging.jar" else activity_build
        (system / relative).write_bytes((build / name).read_bytes())
    return {"files": changes, "camera_apk_unchanged": True,
            "global_os_properties_unchanged": True, "screenshot_policy_semantics_unchanged": True,
            "policy_and_package_verification_unchanged": True}


def stagefright_encoder_read_patch(data):
    """Bound the donor encoder's cmdline read, reserving its terminator byte."""
    expected = "91dfcd99d441ab1d5aaf00ab59968f4ad83c8961dfe0119310c2fbab6dbc094d"
    before = bytes.fromhex("e04300912100805202408052e30314aae41f8052f643009112e20594")
    if hashlib.sha256(data).hexdigest() != expected or data.count(before) != 1:
        raise RuntimeError("Unexpected donor stagefright; refusing encoder read patch")
    offset = data.index(before) + 8
    patched = data[:offset] + bytes.fromhex("c21f8052") + data[offset + 4:]
    return patched, {"original_sha256": expected, "sha256": hashlib.sha256(patched).hexdigest(),
                     "file_offset": offset, "instruction_bytes": 4,
                     "requested_read_before": 512, "requested_read_after": 254,
                     "buffer_bytes": 255, "terminator_reserved": True,
                     "fortify_and_encoder_selection_unchanged": True}


def integrate_camera_native(system, native_input):
    """Keep the matching S10 processing stack private to the Camera app."""
    metadata = json.loads((native_input / "input.json").read_text())
    source = native_input / "SamsungCamera"
    destination = system / "priv-app/SamsungCamera"
    if (metadata.get("source_build") != "G973FXXSGHWC1"
            or metadata.get("native_ion_isolated_to_camera") is not True
            or metadata["files"].get("SamsungCamera.apk") != APK_SHA256
            or digest(destination / "SamsungCamera.apk") != APK_SHA256
            or (destination / "lib").exists()):
        raise RuntimeError("Unexpected Camera native input or existing native directory")
    actual_files = {str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()}
    if actual_files != set(metadata["files"]) or any(path.is_symlink() for path in source.rglob("*")):
        raise RuntimeError("Camera native input contains unrecorded files or symlinks")
    if metadata["library_count"] != len(actual_files) - 1:
        raise RuntimeError("Camera native library count differs")
    for relative, expected in metadata["files"].items():
        if relative != "SamsungCamera.apk" and not re.fullmatch(r"lib/arm64/[A-Za-z0-9_.+-]+\.so", relative):
            raise RuntimeError("Unexpected app-private Camera library path")
        if digest(source / relative) != expected:
            raise RuntimeError("Camera native input hash changed: " + relative)
    subprocess.run(["cp", "-a", str(source / "lib"), str(destination / "lib")], check=True)
    files = {"priv-app/SamsungCamera/" + relative: expected for relative, expected in metadata["files"].items()
             if relative.startswith("lib/")}
    for relative, expected in files.items():
        if digest(system / relative) != expected:
            raise RuntimeError("Camera native copy differs: " + relative)
    return {"files": files, "native_input_sha256": digest(native_input / "input.json"),
            "library_count": metadata["library_count"], "global_native_libraries_replaced": False,
            "legacy_ion_soname": "libs10.so", "apk_signature_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--stock-system", type=Path, required=True)
    parser.add_argument("--version-compat", type=Path, required=True)
    parser.add_argument("--activity-compat", type=Path, required=True)
    parser.add_argument("--native-input", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if os.geteuid() != 0 or not args.records.is_dir() or args.records.resolve().is_relative_to(checkout):
        parser.error("Linux root and an existing external records directory are required")
    report_path = args.records / "samsung-camera-integration.json"
    if report_path.exists():
        parser.error("Completed integration records must not be overwritten")
    result = integrate_samsung_camera(args.system, args.stock_system)
    result["compatibility"] = apply_camera_compatibility(args.system, args.version_compat, args.activity_compat)
    result["native_processing"] = integrate_camera_native(args.system, args.native_input)
    path = args.system / "lib64/libstagefright.so"
    patched, result["encoder_read_bound"] = stagefright_encoder_read_patch(path.read_bytes())
    path.write_bytes(patched)
    result["files"].update({relative: item["sha256"] for relative, item in result["compatibility"]["files"].items()})
    result["files"].update(result["native_processing"]["files"])
    result["files"]["lib64/libstagefright.so"] = digest(path)
    with report_path.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
