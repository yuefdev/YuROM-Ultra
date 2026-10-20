#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare verified S10 recovery/AVB inputs; this script never flashes a phone."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

TWRP_SHA256 = "d2b105f5678b618131ecac7aa963c19eb464a9bb924c04cf1747c3380cabfb12"
AVB_COMMIT = "c92ce4cb9a1b6d20a1bc11b7e5864af9f78615bb"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twrp", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    layout = json.loads((checkout / "target/beyond1lte/oneui9/stock-layout.json").read_text())
    stock = json.loads((args.stock / "input.json").read_text())
    twrp = json.loads((args.twrp.parent / "input.json").read_text())
    avb_source = checkout / "external/android-tools/vendor/avb"
    avbtool = avb_source / "avbtool.py"
    commit = subprocess.check_output(["git", "-C", str(avb_source), "rev-parse", "HEAD"], text=True).strip()
    if commit != AVB_COMMIT or stock.get("model") != "SM-G973F" or stock.get("build") != "G973FXXSGHWC1":
        parser.error("Pinned AVB source and the original verified HWC1 cache are required")
    if twrp.get("device") != "beyond1lte" or not twrp.get("publisher_checksum_verified") or digest(args.twrp) != TWRP_SHA256:
        parser.error("The verified official beyond1lte TWRP archive is required")
    original_vbmeta = args.stock / "images/vbmeta.img"
    if digest(original_vbmeta) != stock["images"]["vbmeta.img"]["sha256"]:
        parser.error("Original stock AVB input checksum mismatch")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("A new output below an existing cache parent is required")
    args.output.mkdir()
    recovery = args.output / "recovery.img"
    with tarfile.open(args.twrp) as archive:
        entries = archive.getmembers()
        if len(entries) != 1 or entries[0].name != "recovery.img" or not entries[0].isfile():
            raise RuntimeError("Unexpected recovery TAR contents")
        if entries[0].size > layout["partitions"]["recovery"]["bytes"]:
            raise RuntimeError("Recovery image exceeds the measured S10 recovery partition")
        with archive.extractfile(entries[0]) as source, recovery.open("xb") as output:
            shutil.copyfileobj(source, output, 1024 * 1024)
    with recovery.open("rb") as stream:
        if stream.read(8) != b"ANDROID!":
            raise RuntimeError("Recovery image is not a supported Android boot image")
    vbmeta = args.output / "vbmeta.img"
    subprocess.run([sys.executable, str(avbtool), "make_vbmeta_image", "--output", str(vbmeta),
                    "--algorithm", "NONE", "--flags", "3", "--padding_size", str(layout["partitions"]["vbmeta"]["bytes"]),
                    "--include_descriptors_from_image", str(original_vbmeta)], check=True)
    module_spec = importlib.util.spec_from_file_location("s10_avbtool", avbtool)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    with vbmeta.open("rb") as stream:
        header = module.AvbVBMetaHeader(stream.read(256))
    if header.flags != 3 or header.algorithm_type != 0 or vbmeta.stat().st_size != layout["partitions"]["vbmeta"]["bytes"]:
        raise RuntimeError("Unexpected disabled-AVB bootstrap header or size")
    avb = module.Avb()
    original_descriptors = avb._parse_image(module.ImageHandler(str(original_vbmeta), read_only=True))[2]
    bootstrap_descriptors = avb._parse_image(module.ImageHandler(str(vbmeta), read_only=True))[2]
    if sorted(item.encode() for item in original_descriptors) != sorted(item.encode() for item in bootstrap_descriptors):
        raise RuntimeError("Bootstrap AVB descriptors differ from the original stock descriptors")
    package = args.output / "S10_G973F_TWRP_AVB_bootstrap.tar"
    with tarfile.open(package, "x", format=tarfile.USTAR_FORMAT) as archive:
        for image in (vbmeta, recovery):
            archive.add(image, arcname=image.name, recursive=False)
    with tarfile.open(package) as archive:
        if [entry.name for entry in archive.getmembers()] != ["vbmeta.img", "recovery.img"]:
            raise RuntimeError("Recovery bootstrap includes an unexpected partition")
        for image in (vbmeta, recovery):
            with archive.extractfile(image.name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest(image):
                    raise RuntimeError("Packaged recovery bootstrap image checksum mismatch")
    result = {"schema": 1, "kind": "verified-g973f-recovery-avb-bootstrap", "model": "SM-G973F",
              "twrp_archive_sha256": TWRP_SHA256, "avb_source_commit": commit,
              "original_vbmeta_sha256": stock["images"]["vbmeta.img"]["sha256"],
               "flags": header.flags, "algorithm": "NONE", "stock_descriptors_retained": True,
               "stock_descriptor_count": len(original_descriptors),
              "images": {image.name: {"size": image.stat().st_size, "sha256": digest(image)} for image in (vbmeta, recovery)},
              "package": {"name": package.name, "sha256": digest(package)},
              "repartition": False, "phone_partitions_written": False, "phone_data_formatted": False,
              "device_boot_tested": False, "data_reset_may_be_required": True}
    with (args.output / "input.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
