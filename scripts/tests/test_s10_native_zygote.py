#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove the actual ARM64 mask keeps every kernel-supported capability drop."""

import argparse
import importlib.util
from pathlib import Path
import struct


def decode_mask(instruction):
    word, = struct.unpack("<I", instruction)
    assert word & 0xFFC003FF == 0xB24003E9  # ORR X9, XZR, non-rotated 64-bit mask
    assert (word >> 16) & 63 == 0
    return (1 << (((word >> 10) & 63) + 1)) - 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("s10_native_zygote",
        Path(__file__).resolve().parents[1] / "s10_native_zygote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = (args.system / "lib64/libzygote.dylib.so").read_bytes()
    patched, metadata = module.capability_mask_patch(original)
    offset = metadata["file_offset"]
    assert patched[:offset] == original[:offset] and patched[offset+4:] == original[offset+4:]
    before, after = decode_mask(original[offset:offset+4]), decode_mask(patched[offset:offset+4])
    assert before == (1 << 41) - 1 and after == (1 << 38) - 1
    for whitelist in [0, before, after, *[1 << cap for cap in range(64)]]:
        drop_before, drop_after = before & ~whitelist, after & ~whitelist
        for capability in range(38):
            assert bool(drop_before & (1 << capability)) == bool(drop_after & (1 << capability))
        assert drop_after >> 38 == 0
    for invalid in (patched, original[:offset] + b"\0\0\0\0" + original[offset+4:]):
        try:
            module.capability_mask_patch(invalid)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Unknown/already-patched input must be rejected")
    print("Passed actual ARM64 mask decoding, all 38 supported capability drops and input guards.")


if __name__ == "__main__":
    main()
