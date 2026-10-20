#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise every native preference without retaining test values or initial-state history."""
import argparse
import json
from pathlib import Path
import subprocess

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb",type=Path,required=True);p.add_argument("--serial",required=True)
    p.add_argument("--probe",type=Path,required=True);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--section",default="all");p.add_argument("--keys",help="Optional comma-separated subset for focused retries")
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.records.exists() or not a.records.parent.is_dir() or a.records.resolve().is_relative_to(root):p.error("New external records directory required")
    a.records.mkdir();adb=[str(a.adb),"-s",a.serial]
    def run(*args,check=True,timeout=120):return subprocess.run([*adb,*args],check=check,capture_output=True,timeout=timeout).stdout
    def sh(s):return run("shell",s).decode(errors="replace").strip()
    if sh("id -u")!="0":raise RuntimeError("Root ADB is required")
    features=json.loads((root/"packages/ArtisanControl/features.json").read_text(encoding="utf-8"))
    before={f.get("namespace","global")+":"+f["key"]:sh("settings get "+f.get("namespace","global")+" "+f["key"])
            for f in features if f["type"]!="action"}
    before["secure:clock_seconds"]=sh("settings get secure clock_seconds")
    (a.records/"settings-before.json").write_text(json.dumps(before,indent=2))
    preference="/data/user/0/com.android.settings/shared_prefs/artisan_control_initial.xml"
    present=sh("if [ -f "+preference+" ]; then echo yes; fi")=="yes"
    if present:(a.records/"initial-before.xml").write_bytes(run("exec-out","cat",preference))
    selected=[f for f in features if (a.section=="all" or f["section"]==a.section) and (not a.keys or f["key"] in a.keys.split(","))]
    try:
        run("push",str(a.probe),"/data/local/tmp/ArtisanNativeSettingsProbe.jar")
        results={}
        for index,f in enumerate(selected):
            device="/data/local/tmp/artisan-native-"+a.records.name+"-"+str(index)+".json"
            command="CLASSPATH=/data/local/tmp/ArtisanNativeSettingsProbe.jar app_process /system/bin --nice-name=artisan-native-tests com.artisanrom.tests.NativeSettingsProbe '"+f["section"].replace("'","'\\''")+"' "+device+" '"+f["key"]+"'"
            completed=subprocess.run([*adb,"shell",command],capture_output=True,timeout=120)
            (a.records/(f["key"].replace("@","action-")+".log")).write_bytes(completed.stdout+completed.stderr)
            data=run("exec-out","cat",device,check=False)
            if data.startswith(b"{"):results.update(json.loads(data))
            (a.records/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
            if completed.returncode:raise RuntimeError("Native preference acceptance failed: "+f["key"]+"; see external log")
        expected={f["key"] for f in selected}
        if set(results)!=expected or any(v.get("ui")!="pass" for v in results.values()):raise AssertionError("Preference coverage is incomplete")
        print(json.dumps({"native_ui_preferences_passed":len(results),"section":a.section},ensure_ascii=False))
    finally:
        sh("am force-stop com.android.settings")
        for name,value in before.items():
            space,key=name.split(":",1)
            sh("settings "+("delete "+space+" "+key if value=="null" else "put "+space+" "+key+" '"+value.replace("'","'\\''")+"'"))
        if present:
            run("push",str(a.records/"initial-before.xml"),preference)
            sh("chown 1000:1000 "+preference+"; chmod 660 "+preference+"; restorecon "+preference)
        else:sh("rm -f "+preference+" "+preference+".bak")
        (a.records/"settings-restored.json").write_text(json.dumps({name:sh("settings get "+name.replace(":"," ",1)) for name in before},indent=2))

if __name__=="__main__":main()
