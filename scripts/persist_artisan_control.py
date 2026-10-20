#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Persist a healthy root-ADB trial with a boot watchdog and explicit rollback."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import subprocess
import time

DEVICE="/data/system/artisan-control"
VENDOR="/vendor/etc/artisan-control"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb",type=Path,required=True);p.add_argument("--serial",required=True)
    p.add_argument("--bundle",type=Path,required=True);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--previous-bundle",type=Path,help="Verified previous permanent bundle when replacing boot scripts")
    a=p.parse_args();root=Path(__file__).resolve().parent.parent
    if a.records.exists() or not a.records.parent.is_dir() or a.records.resolve().is_relative_to(root):p.error("A new external records directory is required")
    manifest=json.loads((a.bundle/"manifest.json").read_text());a.records.mkdir()
    previous=json.loads((a.previous_bundle/"manifest.json").read_text()) if a.previous_bundle else None
    if previous and any(manifest["inputs"].get(label)!=spec for label,spec in previous["inputs"].items()):raise ValueError("Original input contract changed")
    for name,expected in manifest["outputs"].items():
        if Path(name).name!=name:raise ValueError("Invalid bundle filename")
        with (a.bundle/name).open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest()!=expected:raise ValueError("Control bundle digest mismatch")
    adb=[str(a.adb),"-s",a.serial]
    def run(*args,check=True):
        result=subprocess.run([*adb,*args],capture_output=True,check=False)
        if check and result.returncode:raise RuntimeError(result.stderr.decode(errors="replace")+result.stdout.decode(errors="replace"))
        return result.stdout
    def sh(command,check=True):return run("shell",command,check=check).decode(errors="replace").strip()
    if sh("id -u")!="0" or sh(f"cat {DEVICE}/trial-result")!="trial-ready":raise RuntimeError("A healthy root trial is required")
    if sh("getenforce")!="Permissive":raise RuntimeError("This live init integration has not been validated against an enforcing policy")
    for relative,expected in manifest.get("required_files",{}).items():
        path=PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or sh("sha256sum /system/"+str(path)).split()[0]!=expected:
            raise RuntimeError("Persistent adapter dependency mismatch: "+relative)
    if sh(f"sha256sum {DEVICE}/broker.jar").split()[0]!=manifest["outputs"]["ArtisanControlBroker.jar"]:raise RuntimeError("Staged broker/bundle mismatch")
    mounts=[]
    for label,spec in manifest["inputs"].items():
        filename=label+Path(spec["path"]).suffix;target="/system/"+spec["path"]
        expected=manifest["outputs"][filename]
        if sh("sha256sum "+target).split()[0]!=expected:raise RuntimeError("Live trial/bundle mismatch: "+label)
        mounts.append((filename,target,expected))
    mount_script=("#!/system/bin/sh\nset -eu\n"+f"base={DEVICE}\n[ -f \"$base/enabled\" ] || exit 0\n")
    for relative,expected in manifest.get("required_files",{}).items():
        mount_script+=f"[ \"$(sha256sum '/system/{relative}' | cut -d ' ' -f1)\" = '{expected}' ] || exit 1\n"
    for filename,target,expected in mounts:
        mount_script+=f"[ \"$(sha256sum \"$base/rom/{filename}\" | cut -d ' ' -f1)\" = '{expected}' ] || exit 1\n"
    mount_script+="mounted=''\nrollback() { for path in $mounted; do umount -l \"$path\" || true; done; }\ntrap rollback EXIT\n"
    for filename,target,expected in mounts:
        mount_script+=f"mount -o bind \"$base/rom/{filename}\" '{target}'\nmounted='{target} '$mounted\n"
    mount_script+="trap - EXIT\n"
    watchdog=("#!/system/bin/sh\nsleep 240\n"+f"[ -f {DEVICE}/enabled ] || exit 0\n"
              +"[ \"$(getprop sys.boot_completed)\" = 1 ] && exit 0\n"
              +f"rm -f {DEVICE}/enabled\nsetprop sys.powerctl reboot,artisan-control-rollback\n")
    broker=("#!/system/bin/sh\n"+f"[ -f {DEVICE}/enabled ] || exit 0\n"
            +f"export CLASSPATH={DEVICE}/broker.jar\nexec /system/bin/app_process /system/bin --nice-name=artisan-control com.artisanrom.control.RootBroker\n")
    rc=("# Portable control hooks; mounting is disabled by removing the enabled marker.\n"
        "on post-fs-data\n"
        f"    exec u:r:vendor_init:s0 root root -- /system/bin/sh {VENDOR}/mount.sh\n"
        "    start vendor.artisan-control-watchdog\n\n"
        f"service vendor.artisan-control-watchdog /system/bin/sh {VENDOR}/watchdog.sh\n"
        "    class core\n    user root\n    group root\n    disabled\n    oneshot\n    seclabel u:r:vendor_init:s0\n\n"
        f"service vendor.artisan-control /system/bin/sh {VENDOR}/broker.sh\n"
        "    class late_start\n    user root\n    group root\n    disabled\n    oneshot\n    seclabel u:r:vendor_init:s0\n\n"
        "on property:sys.boot_completed=1\n    start vendor.artisan-control\n")
    rollback=f"#!/system/bin/sh\nrm -f {DEVICE}/enabled\nsetprop sys.powerctl reboot,artisan-control-rollback\n"
    files={"mount.sh":mount_script,"watchdog.sh":watchdog,"broker.sh":broker,"04-artisan-control.rc":rc,"disable.sh":rollback}
    view=DEVICE+"/vendor-view"
    if sh(f"test -e {view}; echo $?")=="0":raise RuntimeError("Vendor staging view already exists")
    sh(f"mkdir {view}; chmod 700 {view}")
    sh("mount -o remount,rw /vendor")
    mounted=False
    try:
        # A non-recursive bind exposes the writable vendor beneath OEM /vendor/etc overlays.
        sh(f"mount -o bind /vendor {view}");mounted=True
        raw_vendor=view+"/etc/artisan-control"
        exists=sh(f"test -e {raw_vendor}/mount.sh; echo $?")=="0"
        if exists:
            if previous is None:raise RuntimeError("Existing persistent integration requires --previous-bundle")
            old_script=sh(f"cat {raw_vendor}/mount.sh")
            for label,spec in previous["inputs"].items():
                if previous["outputs"][label+Path(spec["path"]).suffix] not in old_script:raise RuntimeError("Previous boot scripts/bundle mismatch")
            for name in files:
                old_target=view+"/etc/init/"+name if name.endswith(".rc") else raw_vendor+"/"+name
                (a.records/("previous-"+name)).write_bytes(run("exec-out","cat",old_target))
        elif previous is not None:raise RuntimeError("Previous persistent integration is absent")
        sh(f"mkdir -p {raw_vendor}; chmod 755 {raw_vendor}; chcon u:object_r:vendor_configs_file:s0 {raw_vendor}")
        for name,text in files.items():
            local=a.records/name;local.write_text(text,newline="\n")
            target=view+"/etc/init/"+name if name.endswith(".rc") else raw_vendor+"/"+name
            run("push",str(local),target+".new")
            if sh("sha256sum "+target+".new").split()[0]!=hashlib.sha256(local.read_bytes()).hexdigest():raise RuntimeError("Init readback mismatch")
            sh(f"chmod 644 {target}.new; chcon u:object_r:vendor_configs_file:s0 {target}.new; mv {target}.new {target}")
        sh(f"touch {DEVICE}/enabled; sync")
    finally:
        if mounted:sh(f"umount {view}")
        sh(f"rmdir {view}")
        run("shell","mount -o remount,ro /vendor",check=False)
        if "(ro," not in sh("mount | grep ' /vendor '"):
            (a.records/"vendor-readonly-on-reboot.txt").write_text("Live read-only remount was busy; the immediate verified reboot must restore it.\n")
    run("reboot")
    run("wait-for-device")
    ready=False
    for _ in range(140):
        time.sleep(2)
        if sh("getprop sys.boot_completed",check=False)=="1":ready=True;break
    if not ready:raise RuntimeError("Boot incomplete; boot watchdog removes the marker and reboots to originals")
    if "(ro," not in sh("mount | grep ' /vendor '"):raise RuntimeError("Vendor did not return to read-only after reboot")
    for filename,target,expected in mounts:
        if sh("sha256sum "+target).split()[0]!=expected:raise RuntimeError("Boot used original files or incorrect hooks")
    sh("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard")
    activity=sh("am start -W -n com.android.settings/.SubSettings --es :settings:show_fragment com.android.settings.artisan.ArtisanSettings"
                if manifest.get("surface")=="native-settings-fragment" else "am start -W -n com.artisanrom.control/.app.MainActivity")
    if "Status: ok" not in activity:raise RuntimeError("Control activity failed after reboot")
    (a.records/"activity.txt").write_text(activity)
    (a.records/"boot.txt").write_text(sh("getprop sys.boot_completed; getprop vendor.s10.performance.state; pidof com.android.systemui; pidof com.sec.android.app.launcher; pidof artisan-control"))
    (a.records/"crashes.txt").write_text(sh("logcat -b crash -d -t 250"),encoding="utf-8")
    user_state=sh("am get-started-user-state 0")
    (a.records/"user-state.txt").write_text(user_state+"\n")
    print(json.dumps({"persistent":True,"reboot_verified":True,"credential_unlock_verified":user_state=="RUNNING_UNLOCKED","rollback":f"sh {VENDOR}/disable.sh"},indent=2))


if __name__=="__main__":main()
