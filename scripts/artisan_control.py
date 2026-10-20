#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install a verified portable control bundle in an already prepared ROM tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil


def digest(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def configure_artisan_control(system,vendor,bundle):
    manifest=json.loads((bundle/"manifest.json").read_text())
    for relative,expected in manifest.get("required_files",{}).items():
        path=PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or digest(system/str(path))!=expected:
            raise ValueError("Unknown adapter dependency: "+relative)
    for name,expected in manifest["outputs"].items():
        if Path(name).name!=name or digest(bundle/name)!=expected:raise ValueError("Control bundle digest mismatch")
    paths=[]
    for label,spec in manifest["inputs"].items():
        relative=PurePosixPath(spec["path"])
        if relative.is_absolute() or ".." in relative.parts:raise ValueError("Invalid adapter target")
        target=system/str(relative);output=bundle/(label+relative.suffix)
        if digest(target)!=spec["sha256"]:raise ValueError("Unknown ROM input: "+label)
        paths.append((target,output))
    init=system/"etc/init/artisan-control.rc"
    broker=system/"framework/artisan-control-broker.jar"
    if manifest.get("surface")!="native-settings-fragment" or "settings" not in manifest["inputs"]:raise ValueError("A native Settings bundle is required")
    if any(path.exists() for path in (init,broker)):raise ValueError("Control already exists in this tree")
    for target,output in paths:
        # Preserve the exact owner, mode and security attributes already assigned by the ROM pipeline.
        with target.open("wb") as stream:stream.write(output.read_bytes())
    reference=system/"priv-app/SecSettings/SecSettings.apk"
    def install(source,target,context_reference):
        shutil.copyfile(source,target);os.chmod(target,0o644);os.chown(target,0,0)
        for key in os.listxattr(context_reference):
            if key=="security.selinux":os.setxattr(target,key,os.getxattr(context_reference,key))
    install(bundle/"ArtisanControlBroker.jar",broker,system/"framework/framework.jar")
    init.write_text('''# Optional privileged operations are served through a peer-UID checked socket.
service artisan-control /system/bin/app_process /system/bin --nice-name=artisan-control com.artisanrom.control.RootBroker
    class late_start
    user root
    group root
    setenv CLASSPATH /system/framework/artisan-control-broker.jar
    disabled

on property:sys.boot_completed=1
    start artisan-control
''')
    for target in (init,):
        os.chmod(target,0o644);os.chown(target,0,0)
        os.setxattr(target,"security.selinux",os.getxattr(reference,"security.selinux"))
    return {"adapter":manifest["adapter"],"features":manifest["features"],"outputs":manifest["outputs"],
            "surface":"native-settings-fragment","settings_resources_unmodified":True,"enforcing_broker_policy_validated":False,
            "framework_changes_require_matched_rollback":True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--system",type=Path,required=True)
    p.add_argument("--vendor",type=Path,required=True);p.add_argument("--bundle",type=Path,required=True);a=p.parse_args()
    if os.geteuid()!=0:p.error("Root is required to preserve Android owners and labels")
    print(json.dumps(configure_artisan_control(a.system,a.vendor,a.bundle),indent=2))


if __name__=="__main__":main()
