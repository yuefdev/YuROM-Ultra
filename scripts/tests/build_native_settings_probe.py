#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a root app_process runner for the real native Settings preferences."""
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
    p.add_argument("--output",type=Path,required=True);p.add_argument("--records",type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.parent.is_dir() or not a.records.is_dir() or a.records.resolve().is_relative_to(ROOT):p.error("New JAR and existing external records directory required")
    source=Path(__file__).parent/"android/artisan-settings/NativeSettingsProbe.java"
    with tempfile.TemporaryDirectory(prefix="native-settings-probe-") as temp,(a.records/"native-probe-build.log").open("w") as log:
        temp=Path(temp);classes=temp/"classes";dex=temp/"dex";classes.mkdir();dex.mkdir()
        run(["javac","--release","11","-classpath",a.android_jar,"-d",classes,source],log)
        run(["java","-cp",a.build_tools/"lib/d8.jar","com.android.tools.r8.D8","--min-api","31","--lib",a.android_jar,"--output",dex,*classes.rglob("*.class")],log)
        with zipfile.ZipFile(a.output,"w") as archive:archive.write(dex/"classes.dex","classes.dex",compress_type=zipfile.ZIP_STORED)
    print("Native Settings probe built")

if __name__=="__main__":main()
