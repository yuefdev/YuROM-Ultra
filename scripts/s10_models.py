#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned Exynos S10 model identities, stock images and original UFS layouts."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "SM-G973F": {"device": "beyond1lte", "build": "G973FXXSGHWC1"},
    "SM-G970F": {
        "device": "beyond0lte", "build": "G970FXXSGHWC2",
        "archive": "3aa7aeae54f7cf8bc07b76e05d674d46e32fc7ef44ac4f609d783292f22cabd9",
        "pit": "73761267f88213abaa2fdfe6a1b79975ea118af03b7268ceea51df4f93f885ca",
        "images": {
            "system.img": "d3a4cac4f74c6d72c46b4d69494176c79e50cebee1e5bbcc730d73741b7b1f0c",
            "vendor.img": "2463fc528e1119be2567c701781fa863c20bb9656685a455335f9136edb4c5cf",
            "boot.img": "6d5547af0957e7d171f11aafe09750442c7f3584e65b34d8cb6883b0ab8da365",
            "dtb.img": "fd8c644f24352ce8dba17a305cff1a366274684fb43cc3a7f9dd1054ad285732",
            "dtbo.img": "45f39ec38fea511c5bfe7630c4cb5c1fa780c9c4bf27873ab3a75456d494b757",
            "vbmeta.img": "2d41ba1abe0cd32001f7930dc820e3fd3152142b3982ba274db5f390f91587e9",
        },
    },
    "SM-G975F": {
        "device": "beyond2lte", "build": "G975FXXSGHWC2",
        "archive": "162fdbd2198ad47ecbd671d212e52ba34634f7fee9ee0bfd7927629e6486fd13",
        "pit": "945a76e67a6d7f427a24837f63438985663f9fe4948588f2185c948dda000155",
        "images": {
            "system.img": "235b1705b20873844de9f0975c18a9cf30eccba5fd97b7deb8dd1c5745ede034",
            "vendor.img": "c4ae9deca8b74bf16d969a04be4bdc83b2a1f62ce55ac6b15a92f1945b6959b8",
            "boot.img": "3814daf26d0b2ab59048d7ea37b616cdcf8e8701be021a7debdf5b45d0a25e7e",
            "dtb.img": "7b59beaa7b642c82bd5b8b7abdc55c39c259c7c3acfc10cf1a911525b335bbc9",
            "dtbo.img": "c03c377027b2a91a8252de1e3da22484a5862345f40b3cb29b0a4e6dacca29cb",
            "vbmeta.img": "ab1c21e6aa357e282e921b616b0d86be4b6d316dbbdcfdbccdf01b9fbbcbf2b7",
        },
    },
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def layout_for(model):
    profile = MODELS[model]
    # All three independently verified stock PITs have these capacities.
    layout = json.loads((ROOT / "target/beyond1lte/oneui9/stock-layout.json").read_text())
    if model != "SM-G973F":
        layout = {"schema": 1, "model": model, "device": profile["device"], "repartition": False,
                  "source": "model stock CSC UFS PIT", "pit_sha256": profile["pit"],
                  "partitions": layout["partitions"]}
    return layout


def pit_entries(data):
    magic, count = struct.unpack_from("<2I", data)
    if magic != 0x12349876 or not 0 < count < 100 or len(data) < 28 + count * 132:
        raise ValueError("Unsupported Samsung PIT header")
    result = {}
    for index in range(count):
        offset = 28 + index * 132
        values = struct.unpack_from("<9I", data, offset)
        name = data[offset + 36:offset + 68].split(b"\0")[0].decode("ascii").lower()
        if values[1] != 8 or not name or name in result:
            raise ValueError("Expected unique original UFS PIT entries")
        # UFS PIT counts use 4096-byte blocks; Linux exposes 512-byte sectors.
        result[name] = {"bytes": values[6] * 4096, "sectors": values[6] * 8}
    return result


def verify_family_stock(root, model):
    profile = MODELS[model]
    manifest = json.loads((root / "input.json").read_text())
    if (manifest.get("kind") != "verified-s10-family-hwc2-stock-inputs" or manifest.get("model") != model
            or manifest.get("build") != profile["build"] or manifest.get("archive_sha256") != profile["archive"]):
        raise ValueError("Model stock provenance does not match the registered firmware")
    for name, expected in profile["images"].items():
        if manifest["images"][name]["sha256"] != expected or digest(root / "images" / name) != expected:
            raise ValueError("Registered model stock image changed: " + name)
    pits = list(root.glob("*.pit"))
    if len(pits) != 1 or digest(pits[0]) != profile["pit"]:
        raise ValueError("The registered model's own CSC PIT is required")
    entries = pit_entries(pits[0].read_bytes())
    for name, spec in layout_for(model)["partitions"].items():
        if name in ("userdata",):
            continue
        if entries[name]["bytes"] != spec["bytes"]:
            raise ValueError("Model PIT capacity does not match the maintained layout: " + name)
    return manifest


def render_installer(model):
    profile = MODELS[model]
    template = (ROOT / "target/beyond1lte/oneui9/installer/update-binary").read_text()
    if model == "SM-G973F":
        return template
    return (template.replace("G973F", model.removeprefix("SM-"))
            .replace("beyond1lte", profile["device"]).replace("beyond1|", profile["device"].removesuffix("lte") + "|")
            .replace("HWC1-base", "HWC2-base"))
