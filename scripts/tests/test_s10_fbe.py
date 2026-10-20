#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the actual kernel's crypto modes and preserve FBE across both fstabs."""
import argparse
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kernel = load("s10_kernel", "build_oneui9_s10_kernel.py")
candidate = load("s10_candidate", "prepare_oneui9_s10_candidate.py")


class FileEncryptionTests(unittest.TestCase):
    def test_actual_kernel_rejects_ice_and_accepts_aes_xts_cts(self):
        policy = (self.kernel_source / "fs/crypto/policy.c").read_text()
        function = re.search(r"static bool fscrypt_valid_enc_modes\(.*?\n}\n", policy, re.S)
        self.assertIsNotNone(function)
        header = self.kernel_source / "include/uapi/linux/fscrypt.h"
        program = (f'#include <stdbool.h>\n#include "{header}"\ntypedef unsigned int u32;\n'
                   + function.group(0)
                   + "int main(void) { return fscrypt_valid_enc_modes(127, 4) || "
                     "!fscrypt_valid_enc_modes(FSCRYPT_MODE_AES_256_XTS, FSCRYPT_MODE_AES_256_CTS); }\n")
        with tempfile.TemporaryDirectory(prefix="s10-fscrypt-predicate-") as temporary:
            path = Path(temporary)
            (path / "probe.c").write_text(program)
            subprocess.run(["cc", "-Wall", "-Werror", str(path / "probe.c"), "-o", str(path / "probe")], check=True)
            subprocess.run([str(path / "probe")], check=True)
        config = self.kernel_config.read_text().splitlines()
        for symbol in ["CONFIG_FS_ENCRYPTION=y", "CONFIG_CRYPTO_AES=y", "CONFIG_CRYPTO_XTS=y", "CONFIG_CRYPTO_CTS=y"]:
            self.assertIn(symbol, config)

    def test_ramdisk_and_vendor_agree_and_keep_all_other_fstab_fields(self):
        original = self.fstab.read_text()
        cached = kernel.cache_first_stage_fstab(original)
        updated = kernel.compatible_fbe_fstab(cached)
        with tempfile.TemporaryDirectory(prefix="s10-fbe-vendor-") as temporary:
            vendor = Path(temporary)
            path = vendor / "etc/fstab.exynos9820"
            path.parent.mkdir()
            path.write_text(cached)
            result = candidate.reconcile_data_encryption(vendor)
            self.assertEqual(path.read_text(), updated)
            self.assertTrue(result["file_encryption_enabled"])
            self.assertTrue(result["requires_clean_data"])
        self.assertEqual(len(cached.splitlines()), len(updated.splitlines()))
        for before, after in zip(cached.splitlines(), updated.splitlines()):
            if not before.lstrip().startswith("#") and before.split()[1:2] == ["/data"]:
                self.assertEqual(after, before.replace("fileencryption=ice", "fileencryption=aes-256-xts:aes-256-cts:v2"))
                self.assertIn("quota", after.split()[4].split(","))
            else:
                self.assertEqual(after, before)

    def test_encryption_is_never_silently_removed_or_rewritten_twice(self):
        original = self.fstab.read_text()
        for text in [original.replace("fileencryption=ice,", ""),
                     original.replace("fileencryption=ice", "fileencryption=unknown"),
                     original.replace("\t/data\t", "\t/other\t"),
                     kernel.compatible_fbe_fstab(original)]:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                kernel.compatible_fbe_fstab(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-fstab", type=Path, required=True)
    parser.add_argument("--kernel-source", type=Path, required=True)
    parser.add_argument("--kernel-config", type=Path, required=True)
    args, extra = parser.parse_known_args()
    FileEncryptionTests.fstab = args.stock_fstab
    FileEncryptionTests.kernel_source = args.kernel_source
    FileEncryptionTests.kernel_config = args.kernel_config
    unittest.main(argv=[__file__] + extra)
