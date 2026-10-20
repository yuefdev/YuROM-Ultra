#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract legacy framework VINTF inputs from the verified original HWC1 image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Linux root, an existing input cache parent and a new output are required")
    stock = json.loads((args.stock / "input.json").read_text())
    if stock.get("kind") != "verified-s10-hwc1-stock-inputs" or stock.get("model") != "SM-G973F" or stock.get("build") != "G973FXXSGHWC1":
        parser.error("The original verified SM-G973F HWC1 inputs are required")
    image = args.stock / "images/system.img"
    checksum = digest(image)
    if checksum != stock["images"]["system.img"]["sha256"]:
        parser.error("Original stock system image checksum mismatch")
    args.output.mkdir()
    with tempfile.TemporaryDirectory(prefix="s10-legacy-vintf-") as temporary:
        mount = Path(temporary)
        subprocess.run(["mount", "-t", "ext4", "-o", "loop,ro,noload", str(image), str(mount)], check=True)
        try:
            for partition in ("system", "system_ext", "product"):
                relative = "system/etc/vintf" if partition == "system" else f"system/{partition}/etc/vintf"
                source = mount / relative
                if source.is_dir():
                    subprocess.run(["cp", "-a", str(source), str(args.output / partition)], check=True)
        finally:
            subprocess.run(["umount", str(mount)], check=True)
    files = {str(path.relative_to(args.output)): digest(path) for path in sorted(args.output.rglob("*.xml"))}
    for name in ("system/compatibility_matrix.device.xml", "system_ext/manifest.xml"):
        if name not in files:
            raise RuntimeError(f"Required original legacy VINTF input is missing: {name}")
    result = {"schema": 1, "kind": "verified-hwc1-legacy-framework-vintf",
              "model": stock["model"], "build": stock["build"], "stock_system_sha256": checksum,
              "files": files, "android_metadata_preserved": True}
    with (args.output / "input.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Imported {len(files)} original HWC1 framework VINTF inputs with Android metadata.")


if __name__ == "__main__":
    main()
