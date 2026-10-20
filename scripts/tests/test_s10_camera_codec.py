#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the real encoder fread setup and its terminator write on ARM64."""
import argparse
import importlib.util
from pathlib import Path
import unittest

from unicorn import Uc, UC_ARCH_ARM64, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0,
                                UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                                UC_ARM64_REG_X4, UC_ARM64_REG_X20)
from test_s10_legacy_mapper import load_segments

spec = importlib.util.spec_from_file_location("s10_camera", Path(__file__).resolve().parents[1] / "prepare_s10_samsung_camera.py")
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


def execute_read(data, contents):
    cpu = Uc(UC_ARCH_ARM64, 0)
    for address, segment in load_segments(data):
        if segment:
            begin, end = address & ~4095, (address + len(segment) + 4095) & ~4095
            cpu.mem_map(begin, end - begin)
            cpu.mem_write(address, segment)
    stack = 0x40000000
    cpu.mem_map(stack, 4096)
    cpu.mem_write(stack + 16, bytes(255) + b"\xa5" * 16)
    cpu.reg_write(UC_ARM64_REG_SP, stack)
    cpu.reg_write(UC_ARM64_REG_X20, 0x12345678)
    observed = {}

    def fread(cpu, address, size, context):
        if address != 0xf3128:
            return
        pointer = cpu.reg_read(UC_ARM64_REG_X0)
        size, count = cpu.reg_read(UC_ARM64_REG_X1), cpu.reg_read(UC_ARM64_REG_X2)
        observed.update(size=size, count=count, capacity=cpu.reg_read(UC_ARM64_REG_X4),
                        stream=cpu.reg_read(UC_ARM64_REG_X3))
        if size * count > observed["capacity"]:
            raise BufferError("FORTIFY: fread exceeds the actual buffer")
        amount = min(len(contents), size * count)
        if amount:
            cpu.mem_write(pointer, contents[:amount])
            cpu.reg_write(UC_ARM64_REG_X0, amount)
            cpu.reg_write(UC_ARM64_REG_PC, address + 4)
        else:
            cpu.emu_stop()

    cpu.hook_add(UC_HOOK_CODE, fread)
    cpu.emu_start(0xf3110, 0xf3134, count=20)
    return observed, bytes(cpu.mem_read(stack + 16, 255)), bytes(cpu.mem_read(stack + 271, 16))


class CameraCodecTests(unittest.TestCase):
    def test_real_call_reproduces_abort_and_reserves_terminator(self):
        original = self.path.read_bytes()
        with self.assertRaises(BufferError):
            execute_read(original, b"com.sec.android.app.camera")
        patched, record = camera.stagefright_encoder_read_patch(original)
        self.assertEqual(len(original), len(patched))
        offset = record["file_offset"]
        self.assertEqual(patched[:offset], original[:offset])
        self.assertEqual(patched[offset + 4:], original[offset + 4:])
        for length in (0, 1, 26, 254, 255, 512):
            observed, buffer, canary = execute_read(patched, b"x" * length)
            self.assertEqual(observed, {"size": 1, "count": 254, "capacity": 255, "stream": 0x12345678})
            copied = min(length, 254)
            self.assertEqual(buffer[:copied], b"x" * copied)
            self.assertEqual(buffer[copied], 0)
            self.assertEqual(canary, b"\xa5" * 16)
        for invalid in (original[:-1], patched):
            with self.assertRaisesRegex(RuntimeError, "Unexpected donor stagefright"):
                camera.stagefright_encoder_read_patch(invalid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stagefright", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    CameraCodecTests.path = args.stagefright
    unittest.main(argv=[__file__] + remaining)
