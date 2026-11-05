#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/utils"))
from astropart_s26_preflight import verify


class DonorPreflightTests(unittest.TestCase):
    def fixture(self, root, donor_build="S948BXXU5BZJA"):
        fw = root / "firmware"
        donor = fw / "SM-S948B_EUX"
        stock = fw / "SM-G975F_AUT"
        kernel = root / "kernel"
        for p in (donor, stock):
            p.mkdir(parents=True)
            (p / ".extracted").touch()
        sys = donor / "system/system"
        (sys / "framework").mkdir(parents=True)
        (sys / "framework/framework.jar").touch()
        (sys / "priv-app/SamsungCamera").mkdir(parents=True)
        (sys / "priv-app/SamsungCamera/SamsungCamera.apk").touch()
        (sys / "build.prop").write_text(
            f"ro.build.version.incremental={donor_build}\nro.build.version.sdk=37\n")
        (donor / "product").mkdir()
        (donor / "system_ext").mkdir()
        (stock / "vendor/etc/vintf").mkdir(parents=True)
        (stock / "vendor/etc/vintf/manifest.xml").touch()
        (stock / "vendor/build.prop").write_text(
            "ro.product.vendor.model=SM-G975F\n"
            "ro.vendor.build.version.incremental=G975FXXSGHWC2\n")
        kernel.mkdir()
        for name in ("boot.img", "dtb.img", "dtbo.img"):
            (kernel / name).write_bytes(b"fixture")
        return fw, kernel

    def test_accept_verified_identity_without_flash_claim(self):
        with tempfile.TemporaryDirectory() as d:
            fw, kernel = self.fixture(pathlib.Path(d))
            report = verify(fw, kernel)
            self.assertEqual(report["model"], "SM-G975F")
            self.assertFalse(report["ready_for_flash"])

    def test_reject_different_s26_build(self):
        with tempfile.TemporaryDirectory() as d:
            fw, kernel = self.fixture(pathlib.Path(d), "S948BXXU6ZZK3")
            with self.assertRaisesRegex(ValueError, "Full public"):
                verify(fw, kernel)

    def test_reject_missing_kernel(self):
        with tempfile.TemporaryDirectory() as d:
            fw, kernel = self.fixture(pathlib.Path(d))
            (kernel / "dtbo.img").unlink()
            with self.assertRaisesRegex(ValueError, "kernel image"):
                verify(fw, kernel)


if __name__ == "__main__":
    unittest.main()
