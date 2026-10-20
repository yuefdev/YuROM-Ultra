#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused adapter-contract and executable wrapper checks."""
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_artisan_control import ROOT,wrap_method,dex_classes


class AdapterContract(unittest.TestCase):
    def test_every_presented_hook_setting_has_an_adapter(self):
        catalogue=json.loads((ROOT/"packages/ArtisanControl/features.json").read_text())
        adapter=runpy.run_path(str(ROOT/"packages/ArtisanControl/adapters/oneui9.py"))["ADAPTER"]
        requested={f["key"] for f in catalogue if f["key"].startswith("ac_")}
        self.assertEqual(requested,set(adapter["features"]))
        self.assertEqual(len(catalogue),len({f["key"] for f in catalogue}))
        for target in adapter["targets"].values():
            paths=[(r["class"],r["method"]) for r in target.get("hooks",[])]
            self.assertEqual(len(paths),len(set(paths)))
            self.assertRegex(target["sha256"],r"^[a-f0-9]{64}$")
            self.assertNotIn("..",Path(target["path"]).parts)

    def test_wrapper_preserves_original_and_assembles_typed_returns(self):
        source='''.class public Lfixture/Methods;
.super Ljava/lang/Object;

.method public sample(JZ)J
    .locals 2
    const-wide/16 v0, 0x2a
    return-wide v0
.end method

.method public static title()Ljava/lang/String;
    .locals 1
    const-string v0, "original"
    return-object v0
.end method

.method public done()V
    .locals 0
    return-void
.end method
'''
        changed=wrap_method(source,"sample(JZ)J")
        changed=wrap_method(changed,"title()Ljava/lang/String;")
        changed=wrap_method(changed,"done()V")
        self.assertIn("invoke-virtual/range {p0 .. p3}, Lfixture/Methods;->acOriginal$sample(JZ)J",changed)
        self.assertIn("invoke-static/range {}, Lfixture/Methods;->acOriginal$title()Ljava/lang/String;",changed)
        self.assertIn('const-string v0, "original"',changed)
        self.assertIn("const-wide/16 v0, 0x2a",changed)
        with tempfile.TemporaryDirectory(prefix="artisan-wrapper-") as temporary:
            folder=Path(temporary);(folder/"Methods.smali").write_text(changed)
            dex=folder/"classes.dex"
            subprocess.run(["smali","a","-o",str(dex),str(folder)],check=True,capture_output=True)
            self.assertEqual(dex_classes(dex.read_bytes()),["Lfixture/Methods;"])

    def test_unknown_or_duplicate_methods_are_rejected(self):
        source=".class public Lfixture/Test;\n.super Ljava/lang/Object;\n"
        with self.assertRaises(ValueError):wrap_method(source,"missing()V")
        native=source+".method public native missing()V\n.end method"
        with self.assertRaises(ValueError):wrap_method(native,"missing()V")


if __name__=="__main__":unittest.main()
