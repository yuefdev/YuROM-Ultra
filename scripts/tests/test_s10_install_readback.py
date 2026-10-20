#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove a mismatched raw write halts installation before subsequent partitions."""
import importlib.util
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "install_oneui9_s10.py"
spec = importlib.util.spec_from_file_location("s10_installer", source)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ReadbackGateTest(unittest.TestCase):
    def test_mismatch_halts_before_boot_write(self):
        commands, verified = [], []
        installation = [{"partition": "system", "size": 4096, "sha256": "a" * 64},
                        {"partition": "boot", "size": 4096, "sha256": "b" * 64}]

        def shell(command, timeout):
            commands.append(command)
            return "c" * 64 + "  -" if command.startswith("head -c") else "write complete"

        with self.assertRaisesRegex(RuntimeError, "readback checksum mismatch: system"):
            installer.write_verified_images(installation, "/data/install", shell, lambda entry, output: verified.append(entry))
        self.assertFalse(verified)
        self.assertFalse(any("/by-name/boot" in command for command in commands))

    def test_matching_readback_records_each_completed_write(self):
        verified, commands = [], []
        installation = [{"partition": name, "size": 4096, "sha256": value * 64,
                         "device": "/dev/block/platform/13d60000.ufs/by-name/" + name}
                        for name, value in (("system", "a"), ("boot", "b"))]

        def shell(command, timeout):
            commands.append(command)
            if command.startswith("head -c"):
                return ("a" if "/by-name/system" in command else "b") * 64 + "  -"
            return "write complete"

        installer.write_verified_images(installation, "/data/install", shell, lambda entry, output: verified.append(entry))
        self.assertEqual([entry["partition"] for entry in verified], ["system", "boot"])
        self.assertTrue(all(entry["readback_verified"] for entry in verified))
        self.assertTrue(all("/dev/block/platform/13d60000.ufs/by-name/" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
