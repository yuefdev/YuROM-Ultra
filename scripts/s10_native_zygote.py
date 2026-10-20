#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bound the pinned native zygote's capability enumeration to the S10 ABI."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

ORIGINAL_SHA256 = "2b673c1c5c98f9137be95974ddd2fea85f9bcb7cbee9b46455ca105bdf594998"
MASK_ADDRESS = 0x29E00
BEFORE = bytes.fromhex("e9a340b2")
AFTER = bytes.fromhex("e99740b2")
INIT = """# The pinned S10 kernel supports capabilities 0 through 37.
on post-fs-data
    mount none /vendor/lib64/s10-native-zygote/libzygote.dylib.so /system/lib64/libzygote.dylib.so bind
"""


def capability_mask_patch(data):
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256 or data[:6] != b"\x7fELF\x02\x01":
        raise RuntimeError("Unexpected native zygote library")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    offsets = []
    for index in range(header[10]):
        kind, flags, offset, address, _, size, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, header[5] + index * header[9])
        if kind == 1 and flags & 1 and address <= MASK_ADDRESS < address + size:
            offsets.append(offset + MASK_ADDRESS - address)
    if len(offsets) != 1:
        raise RuntimeError("Native zygote executable mapping changed")
    offset = offsets[0]
    if data[offset:offset+4] != BEFORE:
        raise RuntimeError("Native zygote capability enumeration changed")
    # Limit the existing drop-set to every capability implemented by Linux 4.14.
    # The whitelist subtraction and all supported capability checks/drops remain.
    patched = data[:offset] + AFTER + data[offset+4:]
    return patched, {"original_sha256": ORIGINAL_SHA256,
                     "sha256": hashlib.sha256(patched).hexdigest(),
                     "file_offset": offset, "virtual_address": MASK_ADDRESS,
                     "instruction_bytes": 4, "kernel_cap_last_cap": 37,
                     "enumerated_mask_before": (1 << 41) - 1,
                     "enumerated_mask_after": (1 << 38) - 1,
                     "supported_capability_drops_preserved": True}


def configure_native_zygote(system, vendor):
    source = system / "lib64/libzygote.dylib.so"
    patched, metadata = capability_mask_patch(source.read_bytes())
    directory = vendor / "lib64/s10-native-zygote"
    rc = vendor / "etc/init/01-s10-native-zygote.rc"
    if (directory.exists() or rc.exists() or not directory.parent.is_dir()
            or not rc.parent.is_dir()):
        raise RuntimeError("Unexpected existing native zygote compatibility override")
    directory.mkdir(mode=0o755)
    os.chown(directory, 0, 0)
    os.setxattr(directory, "security.selinux", os.getxattr(source.parent, "security.selinux"))
    target = directory / source.name
    target.write_bytes(patched)
    os.chown(target, 0, 0)
    os.chmod(target, 0o644)
    os.setxattr(target, "security.selinux", os.getxattr(source, "security.selinux"))
    rc.write_text(INIT)
    os.chown(rc, 0, 0)
    os.chmod(rc, 0o644)
    os.setxattr(rc, "security.selinux", os.getxattr(vendor / "etc/init/init.exynos9820.rc", "security.selinux"))
    metadata["files"] = {str(path.relative_to(vendor)): {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": "0644", "uid": 0, "gid": 0,
        "selinux": os.getxattr(path, "security.selinux").rstrip(b"\0").decode()}
        for path in (target, rc)}
    metadata["device_boot_tested"] = False
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    args = parser.parse_args()
    if not args.vendor.is_dir():
        parser.error("The vendor output parent must exist.")
    (args.vendor / "lib64").mkdir(exist_ok=True)
    metadata = configure_native_zygote(args.system, args.vendor)
    with (args.vendor / "native-zygote-manifest.json").open("x") as output:
        json.dump(metadata, output, indent=2)
        output.write("\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
