#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the native Settings APK and fresh-tree installation preserve OEM resources."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from artisan_control import configure_artisan_control
from build_artisan_control import dex_classes,digest,signing_block

def attributes(path):
    stat=path.stat()
    return stat.st_uid,stat.st_gid,stat.st_mode,{key:os.getxattr(path,key) for key in os.listxattr(path)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--system",type=Path,required=True)
    p.add_argument("--bundle",type=Path,required=True);a=p.parse_args()
    manifest=json.loads((a.bundle/"manifest.json").read_text())
    assert manifest["surface"]=="native-settings-fragment" and manifest["package"]=="com.android.settings"
    assert "ArtisanControl.apk" not in manifest["outputs"]
    for name,expected in manifest["outputs"].items():assert digest(a.bundle/name)==expected
    original=a.system/manifest["inputs"]["settings"]["path"];native=a.bundle/"settings.apk"
    assert signing_block(original.read_bytes())==signing_block(native.read_bytes())
    with zipfile.ZipFile(original) as old,zipfile.ZipFile(native) as new:
        for name in old.namelist():
            if not re.fullmatch(r"classes\d*\.dex",name):assert new.read(name)==old.read(name),name
        before={owner for name in old.namelist() if re.fullmatch(r"classes\d*\.dex",name) for owner in dex_classes(old.read(name))}
        after=[owner for name in new.namelist() if re.fullmatch(r"classes\d*\.dex",name) for owner in dex_classes(new.read(name))]
        assert len(after)==len(set(after)) and before<set(after)
        assert all(owner.startswith("Lcom/android/settings/artisan/") for owner in set(after)-before)
        assert json.loads(new.read("assets/artisan/features.json"))==json.loads((Path(__file__).resolve().parents[2]/"packages/ArtisanControl/features.json").read_text())
    with tempfile.TemporaryDirectory(prefix="native-settings-integration-") as temporary:
        work=Path(temporary);system=work/"system";vendor=work/"vendor";system.mkdir();vendor.mkdir()
        for relative in manifest.get("required_files",{}):
            target=system/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.system/relative,target)
        paths={spec["path"] for spec in manifest["inputs"].values()}
        paths.add("etc/sysconfig/allowed-system-preload-apps.xml")
        for relative in paths:
            source=a.system/relative;target=system/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target);shutil.copystat(source.parent,target.parent)
        init=system/"etc/init";init.mkdir(parents=True);shutil.copystat(a.system/"etc/init",init)
        before={spec["path"]:attributes(system/spec["path"]) for spec in manifest["inputs"].values()}
        allowlist=system/"etc/sysconfig/allowed-system-preload-apps.xml";allowed=allowlist.read_bytes();allowed_metadata=attributes(allowlist)
        metadata=configure_artisan_control(system,vendor,a.bundle)
        for label,spec in manifest["inputs"].items():
            target=system/spec["path"];assert digest(target)==manifest["outputs"][label+target.suffix]
            assert attributes(target)==before[spec["path"]]
        assert allowlist.read_bytes()==allowed and attributes(allowlist)==allowed_metadata
        assert not (system/"priv-app/ArtisanControl").exists()
        broker=system/"framework/artisan-control-broker.jar";assert digest(broker)==manifest["outputs"]["ArtisanControlBroker.jar"]
        assert (system/"etc/init/artisan-control.rc").is_file() and metadata["settings_resources_unmodified"]
        try:configure_artisan_control(system,vendor,a.bundle)
        except ValueError:pass
        else:raise AssertionError("Repeated installation accepted")
    print("PASS: native Settings fragment, OEM resources/certificate identity and fresh-tree metadata.")
    print("PASS: no standalone control APK; existing Samsung preload entries remain unchanged.")

if __name__=="__main__":main()
