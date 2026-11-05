#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source audit regression tests (no image download or device writes)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astropart_audit import (MIB, PLANNING_MIB, REQUIRED_PACKAGES,
                            S26_DONORS, check_source, package_names)


class AstropartAuditTests(unittest.TestCase):
    def test_layout_and_source(self):
        report = check_source(ROOT, "SM-G975F")
        self.assertTrue(all(report["source_checks"].values()), report["source_checks"])
        self.assertFalse(report["phone_boot_confirmed"])
        self.assertFalse(report["flash_ready"])
        self.assertEqual(report["capacity_mib"]["baseline"], {"system": 5700, "vendor": 1100})
        self.assertEqual(report["capacity_mib"]["extra_system_and_vendor"], 5488)
        self.assertEqual(report["device"], "beyond2lte")

    def test_other_family_display(self):
        for model in ("SM-G970F", "SM-G973F"):
            report = check_source(ROOT, model)
            self.assertTrue(report["source_checks"]["s10plus_cutout_matches_reference"])
            self.assertFalse(report["flash_ready"])

    def test_package_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "packages.txt"
            p.write_text("package:com.google.android.gms\n"
                         "package:com.android.vending\n# ignored\n")
            self.assertEqual(package_names(p), {
                "com.google.android.gms", "com.android.vending"})

    def test_opt_in_image_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "system.img"
            path.write_bytes(b"x" * 128)
            report = check_source(ROOT, "SM-G975F", image_dir=Path(temp))
            self.assertEqual(report["image_sizes"]["system"]["file_bytes"], 128)
            self.assertTrue(report["image_sizes"]["system"]["fits_baseline_capacity"])
            self.assertEqual(report["image_sizes"]["vendor"]["error"], "image not provided")

    def test_9_5_internal_not_marked_public(self):
        target = next(p for p in S26_DONORS if p["one_ui"] == "9.5")
        self.assertEqual(target["build"], "S948BXXU6ZZK3")
        self.assertIn("NOT downloadable public donor", target["status"])


if __name__ == "__main__":
    unittest.main()
