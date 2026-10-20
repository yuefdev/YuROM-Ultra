#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the CE hand-off: legacy HAT removed, user/secret/mode and failure path retained."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from s10_ce_storage import CALL,OWNER,REPLACEMENT,patch_smali

FIXTURE=f'''.class public final {OWNER}
.super Ljava/lang/Object;
.method public final unlockCeStorage(I[B[B)V
    .locals 2
    const/4 v0, 0x0
    const/4 v1, 0x0
    const-string p2, "legacy-hat"
{CALL}
    return-void
.end method
'''


class TokenlessCE(unittest.TestCase):
    def test_only_hat_argument_changes_and_result_is_valid_dex(self):
        changed=patch_smali(FIXTURE)
        self.assertEqual(changed.replace(REPLACEMENT,CALL),FIXTURE)
        self.assertIn('const-string p2, "!"\n\n'+CALL,changed)
        self.assertNotIn("move-object p3",changed)
        self.assertNotIn(".catch",changed)
        with tempfile.TemporaryDirectory(prefix="s10-ce-smali-") as temporary:
            folder=Path(temporary);(folder/"Storage.smali").write_text(changed)
            subprocess.run(["smali","a","-a","35","-o",str(folder/"classes.dex"),str(folder)],check=True,capture_output=True)
            self.assertEqual((folder/"classes.dex").read_bytes()[:4],b"dex\n")

    def test_duplicate_unknown_and_relocated_calls_are_rejected(self):
        for source in [patch_smali(FIXTURE),FIXTURE.replace(CALL,CALL+"\n"+CALL),FIXTURE.replace("unlockCeStorage(I[B[B)V","other(I[B[B)V"),FIXTURE.replace(OWNER,"Lother/Storage;"),FIXTURE.replace(CALL,"")]:
            with self.subTest(source=source),self.assertRaises(ValueError):patch_smali(source)


if __name__=="__main__":unittest.main()
