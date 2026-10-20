#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the real donor SDK gate before/after patching with Unicorn 2.1.4."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_ARCH_ARM64, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
from unicorn.arm64_const import UC_ARM64_REG_W0

spec = importlib.util.spec_from_file_location("s10_candidate", Path(__file__).resolve().parents[1] / "prepare_oneui9_s10_candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def load_segments(data):
    if data[4] == 2:
        start = struct.unpack_from("<Q", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 54)
        for index in range(count):
            entry = struct.unpack_from("<IIQQQQQQ", data, start + size * index)
            if entry[0] == 1:
                yield entry[3], data[entry[2]:entry[2] + entry[5]]
    else:
        start = struct.unpack_from("<I", data, 28)[0]
        size, count = struct.unpack_from("<HH", data, 42)
        for index in range(count):
            entry = struct.unpack_from("<IIIIIIII", data, start + size * index)
            if entry[0] == 1:
                yield entry[2], data[entry[1]:entry[1] + entry[4]]


GATES = {
    "arm64": {"constructor": (0x326e8, 0x326f0, 0x32760),
              "inlined_graphic_buffer": (0x33530, 0x33538, 0x335e8),
              "preload": (0x586ac, 0x586b4, 0x586bc)},
    "arm": {"constructor": (0x21906, 0x2190a, 0x21942),
            "preload": (0x3d6aa, 0x3d6ae, 0x3d6b6)},
    "arm64-swcodec": {"constructor": (0x3301c, 0x33024, 0x33094),
                      "inlined_graphic_buffer": (0x33f38, 0x33f40, 0x33ff0),
                      "preload": (0x5aff4, 0x5affc, 0x5b004)},
}


def execute_gate(data, architecture, sdk, site):
    # Includes the inlined GraphicBuffer path used by the real SurfaceFlinger crash.
    compare, legacy, fatal = GATES[architecture][site]
    if architecture != "arm":
        emulator = Uc(UC_ARCH_ARM64, 0)
        register = UC_ARM64_REG_W0
    else:
        emulator = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        register = UC_ARM_REG_R0
    for address, segment in load_segments(data):
        if not segment:
            continue
        start, end = address & ~4095, (address + len(segment) + 4095) & ~4095
        emulator.mem_map(start, end - start)
        emulator.mem_write(address, segment)
    emulator.reg_write(register, sdk)
    reached = []

    def stop_at_result(cpu, address, size, context):
        if address in (legacy, fatal):
            reached.append("legacy" if address == legacy else "fatal")
            cpu.emu_stop()

    emulator.hook_add(UC_HOOK_CODE, stop_at_result)
    emulator.emu_start(compare | (architecture == "arm"), fatal + 4, count=8)
    if len(reached) != 1:
        raise AssertionError("Did not reach the real legacy mapper path or fatal path")
    return reached[0]


class LegacyMapperTests(unittest.TestCase):
    def test_actual_sdk37_gate_reproduction_and_legacy_fallback(self):
        for directory, architecture in (("lib64", "arm64"), ("lib", "arm")):
            original = (self.system / directory / "libui.so").read_bytes()
            patched, _ = candidate.legacy_mapper_patch(original, architecture)
            for site in GATES[architecture]:
                with self.subTest(architecture=architecture, site=site):
                    self.assertEqual(execute_gate(original, architecture, 37, site), "fatal")
                    self.assertEqual(execute_gate(patched, architecture, 37, site), "legacy")
                    self.assertEqual(execute_gate(original, architecture, 35, site), "legacy")
                    self.assertEqual(execute_gate(patched, architecture, 35, site), "legacy")
                    self.assertEqual(execute_gate(patched, architecture, 28, site), "legacy")

    def test_unknown_or_already_patched_donor_is_rejected(self):
        for directory, architecture in (("lib64", "arm64"), ("lib", "arm")):
            original = (self.system / directory / "libui.so").read_bytes()
            patched, _ = candidate.legacy_mapper_patch(original, architecture)
            with self.subTest(architecture=architecture):
                with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                    candidate.legacy_mapper_patch(original[:-1], architecture)
                with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                    candidate.legacy_mapper_patch(patched, architecture)


class SwcodecMapperTests(unittest.TestCase):
    libui = None

    def setUp(self):
        if self.libui is None:
            self.skipTest("An original swcodec libui input is required")
        self.original = self.libui.read_bytes()

    def test_real_media_constructor_inlined_and_preload_gates(self):
        patched, record = candidate.legacy_mapper_patch(self.original, "arm64-swcodec")
        self.assertEqual(len(patched), len(self.original))
        changed = {index for index, (before, after) in enumerate(zip(self.original, patched)) if before != after}
        permitted = {index for site in record["instructions"]
                     for index in range(site["file_offset"], site["file_offset"] + site["bytes"])}
        self.assertLessEqual(changed, permitted)
        self.assertEqual(len(record["instructions"]), 3)
        for site in GATES["arm64-swcodec"]:
            for sdk in (28, 35, 36, 37):
                with self.subTest(site=site, sdk=sdk):
                    self.assertEqual(execute_gate(self.original, "arm64-swcodec", sdk, site),
                                     "fatal" if sdk > 35 else "legacy")
                    self.assertEqual(execute_gate(patched, "arm64-swcodec", sdk, site), "legacy")

    def test_unknown_or_repatched_media_library_is_rejected(self):
        patched, _ = candidate.legacy_mapper_patch(self.original, "arm64-swcodec")
        for data in (self.original[:-1], patched):
            with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                candidate.legacy_mapper_patch(data, "arm64-swcodec")
        with self.assertRaisesRegex(RuntimeError, "Unexpected"):
            candidate.legacy_mapper_patch(self.original, "arm64")


@unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "Android metadata staging requires Linux root")
class MediaCompatibilityIntegrationTests(unittest.TestCase):
    def test_pinned_module_overlay_is_staged_before_service_start(self):
        with tempfile.TemporaryDirectory(prefix="s10-media-integration-") as temporary:
            system = Path(temporary)
            for relative in ("build.prop", "etc/init/hw/init.rc", "apex/com.android.media.swcodec.capex"):
                destination = system / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.system / relative, destination)
            (system / "lib64").mkdir()
            archive = system / "apex/com.android.media.swcodec.capex"
            before = candidate.digest(archive)
            result = candidate.configure_swcodec_and_hwui(system)
            self.assertEqual(candidate.digest(archive), before)
            self.assertEqual(candidate.properties(system / "build.prop")["debug.hwui.renderer"], ["skiagl"])
            self.assertEqual(candidate.digest(system / "lib64/s10-swcodec/libui.so"), result["mapper_patch"]["sha256"])
            self.assertEqual(os.getxattr(system / "lib64/s10-swcodec/libui.so", "security.selinux"),
                             b"u:object_r:system_lib_file:s0")
            text = (system / "etc/init/hw/init.rc").read_text()
            mount = "    mount none /system/lib64/s10-swcodec/libui.so /apex/com.android.media.swcodec/lib64/libui.so bind\n"
            self.assertEqual(text.count(mount), 1)
            self.assertLess(text.index("    wait_for_prop keystore.module_hash.sent true"), text.index(mount))
            self.assertLess(text.index(mount), text.index("    start system_aconfigd_socket_service"))
            self.assertEqual(set(result["files"]), {"lib64/s10-swcodec/libui.so", "etc/init/hw/init.rc", "build.prop"})
            with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                candidate.configure_swcodec_and_hwui(system)

    def test_unknown_apex_is_rejected_before_tree_changes(self):
        with tempfile.TemporaryDirectory(prefix="s10-media-rejection-") as temporary:
            system = Path(temporary)
            for relative in ("build.prop", "etc/init/hw/init.rc"):
                destination = system / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.system / relative, destination)
            (system / "apex").mkdir()
            (system / "apex/com.android.media.swcodec.capex").write_bytes(b"unknown donor")
            before = {str(path.relative_to(system)): path.read_bytes() for path in system.rglob("*") if path.is_file()}
            with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                candidate.configure_swcodec_and_hwui(system)
            self.assertEqual(before, {str(path.relative_to(system)): path.read_bytes()
                                      for path in system.rglob("*") if path.is_file()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-system", type=Path, required=True)
    parser.add_argument("--original-swcodec-libui", type=Path)
    args, extra = parser.parse_known_args()
    LegacyMapperTests.system = args.original_system
    MediaCompatibilityIntegrationTests.system = args.original_system
    SwcodecMapperTests.libui = args.original_swcodec_libui
    unittest.main(argv=[__file__] + extra)
