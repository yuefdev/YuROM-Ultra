#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the own-app secure capture fixture separately from the ROM bundle."""
import argparse
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_artisan_control import ROOT,run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build-tools",type=Path,required=True);p.add_argument("--android-jar",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--icon-pack",action="store_true",help="Build the resource-only compiled-appfilter icon-pack fixture")
    a=p.parse_args()
    if a.output.exists() or not a.output.parent.is_dir() or a.records.resolve().is_relative_to(ROOT) or not a.records.is_dir():
        p.error("New APK output and existing external records directory are required")
    source=Path(__file__).parent/("android/artisan-icons" if a.icon_pack else "android/artisan-control")
    with tempfile.TemporaryDirectory(prefix="artisan-probe-") as temp,(a.records/"probe-build.log").open("w") as log:
        temp=Path(temp);classes=temp/"classes";dex=temp/"dex";classes.mkdir();dex.mkdir()
        if not a.icon_pack:
            run(["javac","--release","8","-classpath",a.android_jar,"-d",classes,*sorted(source.glob("*.java"))],log)
            run(["java","-cp",a.build_tools/"lib/d8.jar","com.android.tools.r8.D8","--min-api","31","--lib",a.android_jar,"--output",dex,*classes.rglob("*.class")],log)
        unsigned=temp/"probe.apk";aligned=temp/"aligned.apk"
        resources=[]
        if a.icon_pack:
            compiled=temp/"resources.zip"
            run([a.build_tools/"aapt2","compile","--dir",source/"res","-o",compiled],log)
            resources=[compiled]
        run([a.build_tools/"aapt2","link","-I",a.android_jar,"--manifest",source/"AndroidManifest.xml","-o",unsigned,*resources],log)
        if not a.icon_pack:
            with zipfile.ZipFile(unsigned,"a") as z:z.write(dex/"classes.dex","classes.dex",compress_type=zipfile.ZIP_STORED)
        run([a.build_tools/"zipalign","-p","4",unsigned,aligned],log)
        run(["java","-jar",a.build_tools/"lib/apksigner.jar","sign","--key",ROOT/"security/aosp_testkey.pk8","--cert",ROOT/"security/aosp_testkey.x509.pem","--out",a.output,aligned],log)
        run(["java","-jar",a.build_tools/"lib/apksigner.jar","verify",a.output],log)
    print("Probe APK built")


if __name__=="__main__":main()
