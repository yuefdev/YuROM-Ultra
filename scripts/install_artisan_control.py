#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage and trial a verified Artisan Control bundle through root ADB."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import time

DEVICE="/data/system/artisan-control"


def digest(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb",type=Path,required=True)
    parser.add_argument("--serial",required=True)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--records",type=Path,required=True)
    parser.add_argument("--previous-bundle",type=Path,help="Explicit verified bundle currently mounted during an update")
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    records=args.records.resolve()
    if records.exists() or not records.parent.is_dir() or records.is_relative_to(root):
        parser.error("A new external records directory is required")
    manifest=json.loads((args.bundle/"manifest.json").read_text())
    previous=json.loads((args.previous_bundle/"manifest.json").read_text()) if args.previous_bundle else None
    if previous and any(manifest["inputs"].get(label)!=spec for label,spec in previous["inputs"].items()):parser.error("Update changes the original input contract")
    for name,expected in manifest["outputs"].items():
        if Path(name).name!=name or digest(args.bundle/name)!=expected:parser.error("Bundle digest mismatch")
    targets={}
    for label,item in manifest["inputs"].items():
        path=PurePosixPath(item["path"])
        if path.is_absolute() or ".." in path.parts:parser.error("Invalid target path")
        filename=label+(".apk" if path.suffix==".apk" else ".jar")
        targets[filename]="/system/"+str(path)
    records.mkdir()
    adb=[str(args.adb),"-s",args.serial]
    def run(*command,check=True):
        result=subprocess.run([*adb,*command],capture_output=True,check=False)
        if check and result.returncode:raise RuntimeError(result.stderr.decode(errors="replace")+result.stdout.decode(errors="replace"))
        return result.stdout
    def shell(command,check=True):return run("shell",command,check=check).decode(errors="replace").strip()
    if shell("id -u")!="0":raise RuntimeError("Root ADB is required")
    for relative,expected in manifest.get("required_files",{}).items():
        path=PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or shell("sha256sum /system/"+str(path)).split()[0]!=expected:
            raise RuntimeError("Live adapter dependency mismatch: "+relative)
    for filename,target in targets.items():
        label=filename.split(".")[0]
        expected=previous["outputs"].get(filename,manifest["inputs"][label]["sha256"]) if previous else manifest["inputs"][label]["sha256"]
        if shell("sha256sum "+target).split()[0]!=expected:
            raise RuntimeError("Live input does not match the pinned adapter: "+label)
    for namespace in ("global","system","secure"):
        (records/(namespace+"-before.txt")).write_text(shell("settings list "+namespace),encoding="utf-8")
    (records/"protected-before.txt").write_text(shell("sha256sum /system/priv-app/SecSettings/SecSettings.apk /vendor/etc/init/02-s10-performance.rc /vendor/etc/s10-performance-profile.sh"))
    if shell(f"test -f {DEVICE}/enabled; echo $?")=="0":
        (records/"persistence-paused.txt").write_text("Existing boot mounts paused until the new trial is verified and persisted.\n")
        shell(f"rm {DEVICE}/enabled; setprop ctl.stop vendor.artisan-control")
    shell(f"mkdir -p {DEVICE}/original {DEVICE}/rom; chmod 700 {DEVICE} {DEVICE}/original {DEVICE}/rom")
    broker=args.bundle/"ArtisanControlBroker.jar"
    if broker.is_file():
        run("push",str(broker),DEVICE+"/broker.jar.new")
        if shell(f"sha256sum {DEVICE}/broker.jar.new").split()[0]!=manifest["outputs"][broker.name]:raise RuntimeError("Broker readback mismatch")
        shell(f"chmod 600 {DEVICE}/broker.jar.new; mv {DEVICE}/broker.jar.new {DEVICE}/broker.jar")
    for filename,target in targets.items():
        label=filename.split(".")[0]
        if not previous or label not in previous["inputs"]:
            shell(f"cp -p {target} {DEVICE}/original/{filename}")
        run("push",str(args.bundle/filename),DEVICE+"/rom/"+filename+".new")
        if shell(f"sha256sum {DEVICE}/rom/{filename}.new").split()[0]!=manifest["outputs"][filename]:
            raise RuntimeError("Device readback mismatch: "+filename)
        shell(f"chmod 644 {DEVICE}/rom/{filename}.new; chcon u:object_r:system_file:s0 {DEVICE}/rom/{filename}.new; mv {DEVICE}/rom/{filename}.new {DEVICE}/rom/{filename}")
    rollback=("#!/system/bin/sh\n"+f"rm -f {DEVICE}/enabled {DEVICE}/trial-ok\n"
              +"setprop ctl.stop vendor.artisan-control\nsetprop ctl.stop artisan-control\n"
              +'pids=$(pidof artisan-control); [ -z "$pids" ] || kill $pids\n')
    for target in reversed(list(targets.values())):rollback+="umount -l "+target+" 2>/dev/null\n"
    rollback+="setprop ctl.restart zygote\n"
    (records/"rollback.sh").write_text(rollback,newline="\n")
    run("push",str(records/"rollback.sh"),DEVICE+"/rollback.sh")
    watchdog=("#!/system/bin/sh\nsleep 210\n"+f"if [ ! -f {DEVICE}/trial-ok ]; then\n"
              +f"  sh {DEVICE}/rollback.sh\n  echo rolled-back > {DEVICE}/trial-result\nfi\n")
    (records/"watchdog.sh").write_text(watchdog,newline="\n")
    run("push",str(records/"watchdog.sh"),DEVICE+"/watchdog.sh")
    if manifest.get("surface")=="native-settings-fragment":
        shell("am force-stop com.android.settings")
        shell("if [ -f /data/user/0/com.artisanrom.control/shared_prefs/initial.xml ] && [ ! -f /data/user/0/com.android.settings/shared_prefs/artisan_control_initial.xml ]; then mkdir -p /data/user/0/com.android.settings/shared_prefs; cp /data/user/0/com.artisanrom.control/shared_prefs/initial.xml /data/user/0/com.android.settings/shared_prefs/artisan_control_initial.xml; chown 1000:1000 /data/user/0/com.android.settings/shared_prefs/artisan_control_initial.xml; chmod 660 /data/user/0/com.android.settings/shared_prefs/artisan_control_initial.xml; restorecon -RF /data/user/0/com.android.settings/shared_prefs; fi")
    else:
        run("install","-r",str(args.bundle/"ArtisanControl.apk"))
        shell("pm grant com.artisanrom.control android.permission.WRITE_SECURE_SETTINGS")
        shell("appops set com.artisanrom.control WRITE_SETTINGS allow")
    shell(f"rm -f {DEVICE}/trial-ok; echo pending > {DEVICE}/trial-result")
    shell(f"nohup sh {DEVICE}/watchdog.sh > {DEVICE}/watchdog.log 2>&1 < /dev/null &")
    shell("pid=$(pidof artisan-control); if [ -n \"$pid\" ]; then kill $pid; fi",check=False)
    for filename,target in targets.items():
        if previous and filename.split(".")[0] in previous["inputs"]:shell("umount -l "+target)
        shell(f"mount -o bind {DEVICE}/rom/{filename} {target}")
    shell("setprop sys.boot_completed 0; setprop ctl.stop zygote")
    time.sleep(2)
    shell(f"mkdir -p {DEVICE}/cache-backup")
    for filename,target in targets.items():
        if not filename.endswith(".apk"):continue
        prefix=target.lstrip("/").replace("/","@")+"@classes."
        shell(f"for cache in /data/dalvik-cache/arm64/{prefix}*; do if [ -f \"$cache\" ]; then cp -p \"$cache\" {DEVICE}/cache-backup/ && rm \"$cache\"; fi; done")
    shell("setprop ctl.start zygote")
    ready=False
    for attempt in range(90):
        time.sleep(2)
        state=shell("getprop sys.boot_completed",check=False)
        if state=="1":
            user_state=shell("am get-started-user-state 0",check=False)
            (records/"user-state.txt").write_text(user_state+"\n")
            if user_state!="RUNNING_UNLOCKED":continue
            shell("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard",check=False)
            command=("am start -W -n com.android.settings/.SubSettings --es :settings:show_fragment com.android.settings.artisan.ArtisanSettings"
                     if manifest.get("surface")=="native-settings-fragment" else "am start -W -n com.artisanrom.control/.app.MainActivity")
            result=shell(command,check=False)
            (records/"activity-start.txt").write_text(result)
            shell("am start -a android.intent.action.MAIN -c android.intent.category.HOME",check=False)
            time.sleep(3)
            processes=shell("pidof com.android.systemui; pidof com.sec.android.app.launcher",check=False)
            (records/"processes.txt").write_text(processes)
            if len(processes.splitlines())==2 and "Status: ok" in result:
                ready=True;break
    (records/"crashes.txt").write_text(shell("logcat -b crash -d -t 250",check=False),encoding="utf-8")
    (records/"control-log.txt").write_text(shell("logcat -d -t 1000 -s ArtisanControl AndroidRuntime",check=False),encoding="utf-8")
    if not ready:
        shell(f"sh {DEVICE}/rollback.sh",check=False)
        raise RuntimeError("Trial did not reach a healthy UI; original mounts restored")
    shell(f"touch {DEVICE}/trial-ok; echo trial-ready > {DEVICE}/trial-result")
    shell(f"CLASSPATH={DEVICE}/broker.jar nohup /system/bin/app_process /system/bin --nice-name=artisan-control com.artisanrom.control.RootBroker > {DEVICE}/broker.log 2>&1 < /dev/null &")
    (records/"protected-after.txt").write_text(shell("sha256sum /system/priv-app/SecSettings/SecSettings.apk /vendor/etc/init/02-s10-performance.rc /vendor/etc/s10-performance-profile.sh"))
    def protected(path):return [line for line in path.read_text().splitlines() if line.strip() and not (manifest.get("surface")=="native-settings-fragment" and "/SecSettings.apk" in line)]
    if protected(records/"protected-before.txt")!=protected(records/"protected-after.txt"):
        raise RuntimeError("A protected file changed")
    print(json.dumps({"trial_ready":True,"credential_unlock_verified":True,"persistent":False,"rollback":f"sh {DEVICE}/rollback.sh"},indent=2))


if __name__=="__main__":main()
