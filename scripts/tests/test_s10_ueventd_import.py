#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove early ueventd reaches the pinned TEEGRIS permissions without extra allows."""
import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("s10_candidate", Path(__file__).resolve().parents[1] / "prepare_oneui9_s10_candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class UeventdImportTests(unittest.TestCase):
    def test_real_target_imports_reach_stock_teegris_rule(self):
        donor = (self.candidate / "tree/system/etc/ueventd.rc").read_text()
        stock = (self.candidate / "vendor/ueventd.rc").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            system, vendor = root / "system", root / "vendor"
            (system / "etc").mkdir(parents=True)
            (vendor / "etc").mkdir(parents=True)
            path = system / "etc/ueventd.rc"
            path.write_text(donor)
            (vendor / "ueventd.rc").write_bytes(stock)

            def imported_tee_rule():
                pending = [path]
                seen = set()
                result = []
                while pending:
                    item = pending.pop(0)
                    if item in seen or not item.exists():
                        continue
                    seen.add(item)
                    for line in item.read_text().splitlines():
                        fields = line.split()
                        if fields[:1] == ["import"]:
                            pending.append(root / fields[1].lstrip("/"))
                        if fields[:1] == ["/dev/tzdev"]:
                            result.append(fields[1:])
                return result

            self.assertEqual(imported_tee_rule(), [])
            candidate.import_legacy_ueventd_rules(system, vendor)
            self.assertEqual(imported_tee_rule(), [["0666", "system", "system"]])
            self.assertEqual((vendor / "ueventd.rc").read_bytes(), stock)
            self.assertEqual(path.read_text().replace("import /vendor/ueventd.rc\n", "", 1), donor)
            modified = path.read_text()
            with self.assertRaises(RuntimeError):
                candidate.import_legacy_ueventd_rules(system, vendor)
            self.assertEqual(path.read_text(), modified)
            path.write_text(donor)
            (vendor / "etc/ueventd.rc").write_text("# Unexpected competing rules\n")
            with self.assertRaises(RuntimeError):
                candidate.import_legacy_ueventd_rules(system, vendor)
            self.assertEqual(path.read_text(), donor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    args, extra = parser.parse_known_args()
    UeventdImportTests.candidate = args.candidate
    unittest.main(argv=[__file__] + extra)
