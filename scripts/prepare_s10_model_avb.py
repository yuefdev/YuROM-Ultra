#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare model-specific disabled-AVB metadata, retaining stock descriptors."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from prepare_s10_recovery_bootstrap import AVB_COMMIT
from s10_models import MODELS, ROOT, digest, layout_for, verify_family_stock


def prepare(stock_root, output, model):
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Use a new directory under the existing input cache")
    stock = verify_family_stock(stock_root, model)
    avb_source = ROOT / "external/android-tools/vendor/avb"
    if subprocess.check_output(["git", "-C", str(avb_source), "rev-parse", "HEAD"], text=True).strip() != AVB_COMMIT:
        raise ValueError("The pinned AVB tool source is required")
    tool = avb_source / "avbtool.py"
    original = stock_root / "images/vbmeta.img"
    output.mkdir()
    target = output / "vbmeta.img"
    capacity = layout_for(model)["partitions"]["vbmeta"]["bytes"]
    subprocess.run([sys.executable, str(tool), "make_vbmeta_image", "--output", str(target), "--algorithm", "NONE",
                    "--flags", "3", "--padding_size", str(capacity), "--include_descriptors_from_image", str(original)], check=True)
    spec = importlib.util.spec_from_file_location("s10_family_avbtool", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    header = module.AvbVBMetaHeader(target.read_bytes()[:256])
    avb = module.Avb()
    before = avb._parse_image(module.ImageHandler(str(original), read_only=True))[2]
    after = avb._parse_image(module.ImageHandler(str(target), read_only=True))[2]
    if (header.flags != 3 or header.algorithm_type != 0 or target.stat().st_size != capacity
            or sorted(item.encode() for item in before) != sorted(item.encode() for item in after)):
        raise RuntimeError("Model AVB descriptor/header preservation failed")
    result = {"schema": 1, "kind": "verified-s10-model-avb", "model": model, "stock_build": stock["build"],
              "avb_source_commit": AVB_COMMIT, "original_vbmeta_sha256": stock["images"]["vbmeta.img"]["sha256"],
              "flags": 3, "algorithm": "NONE", "stock_descriptors_retained": True, "stock_descriptor_count": len(before),
              "images": {"vbmeta.img": {"size": target.stat().st_size, "sha256": digest(target)}}, "device_partitions_written": False}
    (output / "input.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("SM-G970F", "SM-G975F"), required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.stock, args.output, args.model)
