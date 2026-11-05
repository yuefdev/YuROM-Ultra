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

    def test_g975_hardware_target_is_not_s10(self):
        target = ROOT / "target/beyond2lte"
        cfg = (target / "config.sh").read_text()
        self.assertIn('TARGET_CODENAME="beyond2lte"', cfg)
        self.assertIn('TARGET_ASSERT_MODEL=("SM-G975F")', cfg)
        self.assertIn('TARGET_FIRMWARE="SM-G975F/AUT"', cfg)
        self.assertIn('TARGET_SYSTEM_PARTITION_SIZE=5976883200', cfg)
        self.assertIn('TARGET_VENDOR_PARTITION_SIZE=1153433600', cfg)
        self.assertNotIn("user-repartition-20260913", cfg)
        self.assertNotIn("SM-G973F", cfg)
        self.assertNotIn("/356262101234561", cfg)
        features = (target / "sff.sh").read_text()
        self.assertIn("type:b2", features)
        self.assertIn("siop_beyond2_exynos9820", features)
        self.assertIn("CONFIG_NAVIGATION_BAR_THEME", features)

    def test_s10plus_overlay_matches_reference_path(self):
        import xml.etree.ElementTree as ET
        target = ROOT / "target/beyond2lte/overlay/values"
        root = ET.parse(target / "strings.xml").getroot()
        actual = root.find("string[@name='config_mainBuiltInDisplayCutout']").text
        profiles = json.loads((ROOT / "target/beyond1lte/oneui9/display/profiles.json").read_text())
        self.assertEqual(actual, profiles["models"]["SM-G975F"]["cutout"])
        sizes = ET.parse(target / "dimens.xml").getroot()
        dim_names = {entry.attrib.get("name") for entry in sizes}
        self.assertIn("status_bar_camera_side_padding", dim_names)
        self.assertIn("status_bar_height_portrait", dim_names)

    def test_all_three_google_packages_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            system = Path(folder)
            for name in ("PrebuiltGmsCore", "GoogleServicesFramework", "Phonesky"):
                destination = system / "product" / "priv-app" / name / (name + ".apk")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"fixture")
            camera = system / CAMERA_APK
            camera.parent.mkdir(parents=True, exist_ok=True)
            camera.write_bytes(b"modern-camera-fixture")
            result = inventory_packages(system)
            self.assertTrue(all(result[k] for k in ("gms", "gsf", "play_store", "modern_camera")))

    def test_pinned_public_donor_is_not_9_5(self):
        self.assertEqual(PUBLIC_BUILDS, frozenset({"S948BXXU5BZJA"}))


if __name__ == "__main__":
    unittest.main()
