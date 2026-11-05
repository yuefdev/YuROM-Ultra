#!/usr/bin/env python3
"""Unit tests for S26 Ultra -> G975F preparation contracts (no firmware needed)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astropart_s26_port import (DONOR_MODEL, MODEL, PUBLIC_BUILDS,
                                CAMERA_APK, inventory_packages,
                                update_model_identity, preflight_donor)


class S26UltraPortTest(unittest.TestCase):
    def test_identity_substitutions_keep_framework_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for component in ("system", "system_ext", "product"):
                path = (root / "build.prop" if component == "system" else
                        root / component / "etc/build.prop")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"ro.product.{component}.model=SM-S948B\n"
                                f"ro.product.{component}.device=e3q\n"
                                f"ro.product.{component}.name=e3qxxx\n")
            result = update_model_identity(root)
            self.assertEqual(result["model"], MODEL)
            self.assertIn("ro.product.system.model=SM-G975F", (root / "build.prop").read_text())
            self.assertIn("ro.product.system_ext.device=beyond2", (root / "system_ext/etc/build.prop").read_text())

    def test_missing_service_not_falsely_passed(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / CAMERA_APK).parent.mkdir(parents=True)
            (p / CAMERA_APK).write_bytes(b"test-not-a-real-apk")
            result = inventory_packages(p)
            self.assertEqual(result["modern_camera"], [CAMERA_APK])
            self.assertFalse(result["gms"])
            self.assertFalse(result["play_store"])

    def test_unverified_9_5_donor_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            (d / "input.json").write_text(json.dumps({
                "model": DONOR_MODEL, "kind": "verified-oneui9-donor",
                "build": "S948BXXU6ZZK3",
            }))
            with self.assertRaisesRegex(ValueError, "not public"):
                preflight_donor(d)

    def test_pinned_public_donor_is_not_9_5(self):
        self.assertEqual(PUBLIC_BUILDS, frozenset({"S948BXXU5BZJA"}))


if __name__ == "__main__":
    unittest.main()
