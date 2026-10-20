#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the actual init decision and check scoped S10 display/ADB contracts."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from unicorn import Uc, UC_ARCH_ARM64, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_W0
from test_s10_legacy_mapper import load_segments

spec = importlib.util.spec_from_file_location("s10_candidate", Path(__file__).resolve().parents[1] / "prepare_oneui9_s10_candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def execute_init_decision(data, current_mode):
    emulator = Uc(UC_ARCH_ARM64, 0)
    for address, segment in load_segments(data):
        if not segment:
            continue
        begin, end = address & ~4095, (address + len(segment) + 4095) & ~4095
        emulator.mem_map(begin, end - begin)
        emulator.mem_write(address, segment)
    result = []

    def observe(cpu, address, size, context):
        if address == 0x9c977c:
            cpu.reg_write(UC_ARM64_REG_W0, current_mode & 0xffffffff)
            cpu.reg_write(UC_ARM64_REG_PC, address + 4)
        elif address == 0x9c978c:
            result.append(cpu.reg_read(UC_ARM64_REG_W0))
            cpu.emu_stop()
        elif address == 0x9c97a4:
            result.append("unchanged")
            cpu.emu_stop()

    emulator.hook_add(UC_HOOK_CODE, observe)
    emulator.emu_start(0x9c977c, 0x9c97a8, count=10)
    if len(result) != 1:
        raise AssertionError("Did not observe the actual enforcing setup result")
    return result[0]


class DisplayEnforcingTests(unittest.TestCase):
    def test_actual_donor_init_reproduction_and_restored_enforcing(self):
        original = (self.system / "bin/init").read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), "1f061d2da71aaaabcd8a86614a17e0b262012924aac9fca9e5dbf06018749b9b")
        self.assertEqual(execute_init_decision(original, 0), 0)
        self.assertEqual(execute_init_decision(original, 1), "unchanged")
        patched, record = candidate.init_enforcing_patch(original)
        self.assertEqual(execute_init_decision(patched, 0), 1)
        self.assertEqual(execute_init_decision(patched, 1), "unchanged")
        self.assertEqual(sum(a != b for a, b in zip(original, patched)), 1)
        self.assertEqual(len(original), len(patched))
        self.assertEqual(record["instruction_bytes"], 4)
        for unknown in (original[:-1], patched):
            with self.assertRaisesRegex(RuntimeError, "Unexpected donor init"):
                candidate.init_enforcing_patch(unknown)

    def test_only_maintained_s10_brightness_aod_features_change(self):
        original = (self.system / "etc/floating_feature.xml").read_text()
        maintained = (Path(__file__).resolve().parents[2] / "target/beyond1lte/sff.sh").read_text()
        with tempfile.TemporaryDirectory() as temporary:
            system = Path(temporary)
            (system / "etc").mkdir()
            path = system / "etc/floating_feature.xml"
            path.write_text(original)
            record = candidate.reconcile_s10_display_features(system)
            expected = original
            for name, change in record["features"].items():
                self.assertIn(f"{name}={change['to']}\n", maintained)
                expected = expected.replace(f"<{name}>{change['from']}</{name}>",
                                            f"<{name}>{change['to']}</{name}>", 1)
            self.assertEqual(path.read_text(), expected)
            self.assertEqual(ET.fromstring(expected).findtext("SEC_FLOATING_FEATURE_LCD_SUPPORT_EXTRA_BRIGHTNESS"), "TRUE")
            with self.assertRaisesRegex(RuntimeError, "Unexpected donor display feature"):
                candidate.reconcile_s10_display_features(system)
            invalid = original.replace("<SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_FULLSCREEN>1</", "<SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_FULLSCREEN>9</")
            path.write_text(invalid)
            with self.assertRaises(RuntimeError):
                candidate.reconcile_s10_display_features(system)
            self.assertEqual(path.read_text(), invalid)

    def test_adbd_retains_normal_domain_and_authentication_configuration(self):
        original = (self.system / "etc/init/hw/init.usb.rc").read_text()
        with tempfile.TemporaryDirectory() as temporary:
            system = Path(temporary)
            path = system / "etc/init/hw/init.usb.rc"
            path.parent.mkdir(parents=True)
            path.write_text(original)
            candidate.retain_adbd_domain(system)
            self.assertEqual(path.read_text(), original.replace("service adbd /system/bin/adbd --root_seclabel=u:r:su:s0", "service adbd /apex/com.android.adbd/bin/adbd", 1).replace("    updatable\n", "", 1))
            self.assertIn("    seclabel u:r:adbd:s0\n", path.read_text())
            self.assertNotIn("    updatable\n", path.read_text())
            with self.assertRaises(RuntimeError):
                candidate.retain_adbd_domain(system)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-system", type=Path, required=True)
    args, extra = parser.parse_known_args()
    DisplayEnforcingTests.system = args.original_system
    unittest.main(argv=[__file__] + extra)
