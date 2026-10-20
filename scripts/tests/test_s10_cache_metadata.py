#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify early metadata availability without changing the stock data contract."""
import argparse
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kernel = load("s10_kernel", "build_oneui9_s10_kernel.py")
candidate = load("s10_candidate", "prepare_oneui9_s10_candidate.py")


class CacheMetadataTests(unittest.TestCase):
    def test_cache_mounts_early_and_every_other_fstab_entry_is_unchanged(self):
        original = self.fstab.read_text()
        updated = kernel.cache_first_stage_fstab(original)
        original_lines, updated_lines = original.splitlines(), updated.splitlines()
        self.assertEqual(len(original_lines), len(updated_lines))
        for before, after in zip(original_lines, updated_lines):
            fields = before.split()
            if fields and not before.startswith("#") and fields[1:2] == ["/cache"]:
                self.assertEqual(after.split()[:4], fields[:4])
                self.assertEqual(after.split()[4].split(","), ["wait", "check", "first_stage_mount"])
            else:
                self.assertEqual(after, before)
        data = next(line.split() for line in updated_lines if not line.startswith("#") and line.split()[1:2] == ["/data"])
        self.assertEqual(data[2], "ext4")
        self.assertIn("fileencryption=ice", data[4].split(","))
        self.assertIn("quota", data[4].split(","))

    def test_metadata_precedes_daemon_and_both_paths_keep_identical_selinux_labels(self):
        with tempfile.TemporaryDirectory(prefix="s10-cache-metadata-") as temporary:
            system = Path(temporary)
            for relative in ["etc/init/aconfigd.rc", "etc/selinux/plat_file_contexts"]:
                destination = system / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.system / relative, destination)
            result = candidate.prepare_cache_metadata(system)
            rc = (system / "etc/init/aconfigd.rc").read_text()
            early = rc.split("on early-init\n", 1)[1].split("\non ", 1)[0]
            self.assertLess(early.index("mount none /cache/oneui9-metadata /metadata bind"),
                            early.index("exec_start early_system_aconfigd_platform_init"))
            self.assertLess(early.index("restorecon_recursive /metadata"), early.index("mkdir /metadata/aconfig"))
            contexts = (system / "etc/selinux/plat_file_contexts").read_text().splitlines()
            rules = [line.split() for line in contexts if line.startswith("/metadata")]
            aliases = [line.split() for line in contexts if line.startswith("/cache/oneui9-metadata")]
            self.assertEqual(len(rules), result["file_context_aliases"])
            self.assertEqual(aliases, [[pattern.replace("/metadata", "/cache/oneui9-metadata", 1), label]
                                       for pattern, label in rules])
            for path in ["", "/aconfig", "/aconfig/maps/system.package.map", "/aconfig/flags/system.val"]:
                metadata = [label for pattern, label in rules if re.fullmatch(pattern, "/metadata" + path)]
                backing = [label for pattern, label in aliases if re.fullmatch(pattern, "/cache/oneui9-metadata" + path)]
                self.assertTrue(metadata)
                self.assertEqual(metadata, backing)

    def test_unexpected_cache_flags_are_rejected(self):
        with self.assertRaises(RuntimeError):
            kernel.cache_first_stage_fstab(self.fstab.read_text().replace("wait,check\n", "wait,check,formattable\n", 1))

    def test_vendor_mount_all_skips_the_same_first_stage_cache(self):
        with tempfile.TemporaryDirectory(prefix="s10-vendor-cache-") as temporary:
            vendor = Path(temporary)
            path = vendor / "etc/fstab.exynos9820"
            path.parent.mkdir()
            shutil.copyfile(self.fstab, path)
            candidate.reconcile_first_stage_cache(vendor)
            self.assertEqual(path.read_text(), kernel.cache_first_stage_fstab(self.fstab.read_text()))
            with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                candidate.reconcile_first_stage_cache(vendor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-fstab", type=Path, required=True)
    parser.add_argument("--original-system", type=Path, required=True)
    args, extra = parser.parse_known_args()
    CacheMetadataTests.fstab, CacheMetadataTests.system = args.stock_fstab, args.original_system
    unittest.main(argv=[__file__] + extra)
