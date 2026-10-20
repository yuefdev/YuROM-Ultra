#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove the init property-trie collision is removed while vendor labels survive."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

source = Path(__file__).resolve().parents[1] / "prepare_oneui9_s10_candidate.py"
spec = importlib.util.spec_from_file_location("s10_candidate", source)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class VendorServicePropertyTest(unittest.TestCase):
    def test_only_overlapping_framework_declaration_is_removed(self):
        with tempfile.TemporaryDirectory(prefix="s10-property-regression-") as temporary:
            root = Path(temporary)
            system, vendor = root / "system", root / "vendor"
            framework = system / "system_ext/etc/selinux/system_ext_property_contexts"
            original = vendor / "etc/selinux/vendor_property_contexts"
            framework.parent.mkdir(parents=True)
            original.parent.mkdir(parents=True)
            prefix = "init.svc.vendor.wvkprov_server_hal"
            surrounding = "# framework properties\npersist.sys.test u:object_r:system_prop:s0 exact string\n"
            framework.write_text(surrounding + prefix + " u:object_r:wvkprov_prop:s0\n")
            original.write_text(prefix + " u:object_r:vendor_wvkprov_prop:s0\n")
            vendor_before = original.read_bytes()
            framework.chmod(0o640)
            result = candidate.reconcile_vendor_service_property(system, vendor)
            self.assertEqual(framework.read_text(), surrounding)
            self.assertEqual(original.read_bytes(), vendor_before)
            self.assertEqual(framework.stat().st_mode & 0o777, 0o640)
            self.assertFalse(result["policy_allow_rules_changed"])

    def test_unexpected_context_is_not_removed(self):
        with tempfile.TemporaryDirectory(prefix="s10-property-regression-") as temporary:
            root = Path(temporary)
            framework = root / "system/system_ext/etc/selinux/system_ext_property_contexts"
            original = root / "vendor/etc/selinux/vendor_property_contexts"
            framework.parent.mkdir(parents=True)
            original.parent.mkdir(parents=True)
            framework.write_text("init.svc.vendor.wvkprov_server_hal u:object_r:unexpected_prop:s0\n")
            original.write_text("init.svc.vendor.wvkprov_server_hal u:object_r:vendor_wvkprov_prop:s0\n")
            before = framework.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "Unexpected Widevine"):
                candidate.reconcile_vendor_service_property(root / "system", root / "vendor")
            self.assertEqual(framework.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
