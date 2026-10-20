#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import pinned One UI 9 or HWC1 inputs with Android filesystem metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

import lz4.frame

CHECKSUMS = {
    "donor": "54c851a0db5a2c810f441ab6336aa49766848a6279b58f353b4cc835fbe3ddcd",
    "stock": "eb5f670ea22e6504ce1aad693ecac7e1600a39f565e8775e1c3f6f05be475774",
}
REQUIRED_STOCK = {"system.img", "vendor.img", "boot.img", "recovery.img", "dtb.img", "dtbo.img", "vbmeta.img"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prop(path, key):
    values = [line.split("=", 1)[1].strip() for line in path.read_text().splitlines()
              if "=" in line and not line.lstrip().startswith("#") and line.split("=", 1)[0].strip() == key]
    if len(values) != 1:
        raise RuntimeError(f"Missing or duplicate input property: {key}")
    return values[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=CHECKSUMS)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Linux root, an existing cache parent and a new output are required")
    manifest = json.loads(args.archive.with_suffix(".input.json").read_text())
    if manifest.get("zip_crc") != "passed" or manifest.get("archive_sha256") != CHECKSUMS[args.kind] or digest(args.archive) != CHECKSUMS[args.kind]:
        parser.error("A verified pinned firmware archive is required")
    args.output.mkdir()
    images = args.output / "images"
    images.mkdir()
    members = {}
    with zipfile.ZipFile(args.archive) as archive:
        if args.kind == "donor":
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if len(entries) != 1 or entries[0].filename != "system.img" or entries[0].file_size != 6867423232:
                raise RuntimeError("Unexpected donor archive layout")
            with archive.open(entries[0]) as stream, (images / "system.img").open("xb") as output:
                shutil.copyfileobj(stream, output, 4 * 1024 * 1024)
            members["system.img"] = entries[0].filename
        else:
            ap = [entry for entry in archive.infolist() if Path(entry.filename).name.startswith("AP_") and entry.filename.endswith(".tar.md5")]
            if len(ap) != 1:
                raise RuntimeError("Expected one official HWC1 AP payload")
            with archive.open(ap[0]) as stream, tarfile.open(fileobj=stream, mode="r|", bufsize=1024 * 1024) as payload:
                for entry in payload:
                    name = entry.name.removesuffix(".lz4")
                    if name == "dt.img":
                        name = "dtb.img"
                    if name not in REQUIRED_STOCK | {"product.img"}:
                        continue
                    if not entry.isfile() or entry.size <= 0 or name in members:
                        raise RuntimeError(f"Invalid or duplicate firmware image: {name}")
                    source = payload.extractfile(entry)
                    with source, (images / name).open("xb") as output:
                        if entry.name.endswith(".lz4"):
                            with lz4.frame.LZ4FrameFile(source) as decoded:
                                shutil.copyfileobj(decoded, output, 4 * 1024 * 1024)
                        else:
                            shutil.copyfileobj(source, output, 4 * 1024 * 1024)
                    image = images / name
                    with image.open("rb") as stream:
                        sparse = stream.read(4) == bytes.fromhex("3aff26ed")
                    if sparse:
                        encoded = image.with_suffix(".img.sparse")
                        image.rename(encoded)
                        subprocess.run(["simg2img", str(encoded), str(image)], check=True)
                        encoded.unlink()
                    members[name] = entry.name
                    print(f"Extracted {name}", flush=True)
            if REQUIRED_STOCK - members.keys():
                raise RuntimeError(f"Missing original images: {sorted(REQUIRED_STOCK - members.keys())}")
    mounts = args.output / "mounts"
    mounts.mkdir()
    mounted = []
    try:
        roots = {}
        for name in ("system",) if args.kind == "donor" else ("system", "vendor"):
            mount = mounts / name
            mount.mkdir()
            subprocess.run(["mount", "-t", "ext4", "-o", "loop,ro,noload", str(images / (name + ".img")), str(mount)], check=True)
            mounted.append(mount)
            roots[name] = mount
        system = roots["system"] / "system"
        if args.kind == "donor":
            if prop(system / "build.prop", "ro.build.version.incremental") != "S942BXXU4ZZH6" or prop(system / "build.prop", "ro.build.version.sdk") != "37":
                raise RuntimeError("Pinned donor identity mismatch")
            subprocess.run(["cp", "-a", str(roots["system"]), str(args.output / "tree")], check=True)
        else:
            vendor = roots["vendor"]
            if prop(system / "build.prop", "ro.build.version.incremental") != "G973FXXSGHWC1" or prop(vendor / "build.prop", "ro.product.vendor.model") != "SM-G973F" or prop(vendor / "build.prop", "ro.vendor.build.version.sdk") != "31":
                raise RuntimeError("Original HWC1 identity mismatch")
            subprocess.run(["cp", "-a", str(vendor), str(args.output / "vendor")], check=True)
            selected = args.output / "system-files"
            selected.mkdir()
            wanted = [f"etc/vintf/compatibility_matrix.{level}.xml" for level in (3, 4, 5, 6)]
            for arch in ("lib", "lib64"):
                wanted += [f"{arch}/{name}" for name in (
                    "lib_SoundBooster_ver1000.so", "libsamsungSoundbooster_plus_legacy.so",
                    "vendor.samsung_slsi.hardware.iva@1.0.so", "vendor.samsung_slsi.hardware.MultiFrameProcessing20@1.0.so")]
                wanted += [f"{arch}/libMultiFrameProcessing{version}.camera.samsung.so" for version in ("10", "20", "20Day")]
            for relative in wanted:
                source = system / relative
                if not source.is_file():
                    raise RuntimeError(f"Required original stock input is missing: {relative}")
                destination = selected / "system" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["cp", "-a", str(source), str(destination)], check=True)
    finally:
        for mount in reversed(mounted):
            subprocess.run(["umount", str(mount)], check=True)
    result = {"schema": 1, "kind": "verified-oneui9-donor" if args.kind == "donor" else "verified-s10-hwc1-stock-inputs",
              "archive_sha256": CHECKSUMS[args.kind], "model": "SM-S942B" if args.kind == "donor" else "SM-G973F",
              "build": "S942BXXU4ZZH6" if args.kind == "donor" else "G973FXXSGHWC1",
              "images": {name: {"size": (images / name).stat().st_size, "sha256": digest(images / name), "archive_member": member}
                         for name, member in members.items()}, "device_partitions_written": False}
    with (args.output / "input.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Verified and imported {args.kind} inputs with Android metadata", flush=True)


if __name__ == "__main__":
    main()
