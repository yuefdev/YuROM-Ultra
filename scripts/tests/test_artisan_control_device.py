#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the own-app secure surface, scoped framework hooks and root broker."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from collections import Counter
import socket
import struct
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET

PKG="com.artisanrom.control.probe"
KEYS=("ac_enabled","ac_secure_capture_all","ac_secure_capture_apps","ac_hide_developer_apps","ac_filter_apps",
      "ac_hidden_packages","ac_device_profiles","ac_capture_detection_all","ac_capture_detection_apps",
      "ac_home_enabled","ac_home_grid","ac_apps_grid","ac_recents_enabled","ac_recents_layout",
      "ac_recents_hide_status","ac_recents_hide_clear","ac_icon_pack","ac_hide_privacy")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb",type=Path,required=True);p.add_argument("--serial",required=True)
    p.add_argument("--probe",type=Path,required=True);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--launcher-ui",action="store_true",help="Verify real Samsung app-drawer grids and recents transitions")
    p.add_argument("--icon-pack",type=Path,help="Also verify the compiled-appfilter fixture and live privacy-indicator updates")
    a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if a.records.exists() or not a.records.parent.is_dir() or a.records.resolve().is_relative_to(root):p.error("New external records directory required")
    a.records.mkdir();adb=[str(a.adb),"-s",a.serial]
    def run(*command,check=True):return subprocess.run([*adb,*command],capture_output=True,check=check,timeout=120).stdout
    def shell(command):return run("shell",command).decode(errors="replace").strip()
    def ensure_installed(apk,package):
        paths=run("shell","pm path "+package,check=False).decode(errors="replace").splitlines()
        with apk.open("rb") as stream:expected=hashlib.file_digest(stream,"sha256").hexdigest()
        if len(paths)==1 and paths[0].startswith("package:"):
            installed=paths[0].removeprefix("package:")
            if shell("sha256sum '"+installed.replace("'","'\\''")+"'").split()[0]==expected:return
        run("install","-r",str(apk))
    saved={key:shell("settings get global "+key) for key in KEYS}
    timeout=shell("settings get system screen_off_timeout")
    (a.records/"system-before.json").write_text(json.dumps({"screen_off_timeout":timeout},indent=2))
    (a.records/"settings-before.json").write_text(json.dumps(saved,indent=2))
    port=int(run("forward","tcp:0","localabstract:artisan-control-v1"))
    def broker(command,payload=None):
        with socket.create_connection(("127.0.0.1",port),timeout=60) as client:
            stream=client.makefile("rwb");encoded=command.encode();stream.write(struct.pack(">H",len(encoded))+encoded)
            if payload is not None:stream.write(struct.pack(">i",len(payload))+payload)
            stream.flush();header=stream.read(5)
            if len(header)!=5:raise RuntimeError("Broker did not respond")
            ok,length=struct.unpack(">?i",header)
            if not 0<=length<=64*1024*1024:raise ValueError("Invalid broker response length")
            result=stream.read(length)
            if len(result)!=length:raise RuntimeError("Truncated broker response")
            if not ok:raise RuntimeError(result.decode(errors="replace"))
            return result
    def put(key,value):shell("settings put global "+key+" '"+value.replace("'","'\\''")+"'")
    def launch(name,control_uid=None,extras=""):
        shell("am force-stop "+PKG)
        shell("am start -W -n "+PKG+"/.ProbeActivity"+(" --ei control_uid "+str(control_uid) if control_uid is not None else "")+extras)
        time.sleep(2)
        result=json.loads(shell("cat /data/user/0/"+PKG+"/files/result.json"))
        (a.records/(name+".json")).write_text(json.dumps(result,indent=2))
        (a.records/(name+".png")).write_bytes(run("exec-out","screencap","-p"))
        return result
    def hierarchy(name):
        shell("uiautomator dump /data/local/tmp/artisan-control-ui.xml")
        data=run("exec-out","cat","/data/local/tmp/artisan-control-ui.xml")
        tree=ET.fromstring(data)
        pocket=any("yanlışlıkla dokunma koruması" in n.get("text","").lower() or "accidental touch protection" in n.get("text","").lower() for n in tree.iter("node"))
        if pocket:
            (a.records/(name+"-pocket.xml")).write_bytes(data)
            shell("input swipe 540 1520 540 750 700");time.sleep(1)
            shell("uiautomator dump /data/local/tmp/artisan-control-ui.xml")
            data=run("exec-out","cat","/data/local/tmp/artisan-control-ui.xml");tree=ET.fromstring(data)
        (a.records/(name+".xml")).write_bytes(data)
        (a.records/(name+".png")).write_bytes(run("exec-out","screencap","-p"))
        return tree
    def launcher_ui():
        shell("cmd statusbar collapse")
        for columns in (6,7):
            put("ac_home_grid",str(columns)+"x9");put("ac_apps_grid",str(columns)+"x9")
            broker("restart-home");time.sleep(4)
            shell("input swipe 540 1900 540 650 350");time.sleep(2)
            tree=hierarchy("apps-"+str(columns)+"x9")
            apps=tree.find(".//node[@resource-id='com.sec.android.app.launcher:id/apps_screen']")
            assert apps is not None,"Apps drawer did not open"
            cells=[list(map(int,re.findall(r"\d+",n.get("bounds")))) for n in apps.iter("node")
                   if n.get("resource-id") in ("com.sec.android.app.launcher:id/icon_container","com.sec.android.app.launcher:id/folder_icon_container")]
            assert cells,"No visible app cells"
            assert max(Counter(box[1] for box in cells).values())==columns,cells
            layout=apps.find(".//node[@resource-id='com.sec.android.app.launcher:id/cell_layout']")
            extent=list(map(int,re.findall(r"\d+",layout.get("bounds"))))
            assert abs((extent[3]-extent[1])/9-(cells[0][3]-cells[0][1]))<3,(extent,cells[0])
        results["real_apps_grid_6x9_and_7x9"]=True
        shell("input keyevent KEYCODE_HOME");time.sleep(3)
        since=shell("date '+%m-%d %H:%M:%S.000'")
        shell("am start -W -n com.android.settings/.SubSettings --es :settings:show_fragment com.android.settings.artisan.ArtisanSettings");time.sleep(2)
        shell("input keyevent KEYCODE_APP_SWITCH")
        for attempt in range(20):
            state=shell("dumpsys activity activities")
            if any("topResumedActivity=" in line and "RecentsActivity" in line for line in state.splitlines()):break
            time.sleep(.5)
        else:raise AssertionError("Recents activity did not resume")
        time.sleep(1);hierarchy("recents-hidden")
        shell("input keyevent KEYCODE_HOME");time.sleep(2);hierarchy("recents-restored")
        logs=shell("logcat -d -T '"+since+"' -s ArtisanControl")
        (a.records/"recents-transition.log").write_text(logs,encoding="utf-8")
        assert re.search(r"authorised=true, bars=[1-9]\d*, hidden=true",logs),logs
        assert re.search(r"authorised=true, bars=[1-9]\d*, hidden=false",logs),logs
        results["recents_status_hide_and_restore"]=True
    def icon_and_privacy_ui():
        for key in ("ac_filter_apps","ac_hide_developer_apps"):put(key,"")
        put("ac_device_profiles","{}")
        ensure_installed(a.icon_pack,"com.artisanrom.control.icons.probe")
        fractions={}
        for name,pack in (("icon-pack","com.artisanrom.control.icons.probe"),("icon-restored","")):
            put("ac_icon_pack",pack);broker("restart-home");time.sleep(4)
            shell("input keyevent KEYCODE_WAKEUP");time.sleep(.5)
            shell("wm dismiss-keyguard; cmd statusbar collapse; input keyevent KEYCODE_HOME");time.sleep(1)
            shell("input swipe 540 1900 540 650 350");time.sleep(2);tree=hierarchy(name)
            assert tree.find(".//node[@resource-id='com.sec.android.app.launcher:id/apps_screen']") is not None,"Apps drawer did not open"
            node=next((n for n in tree.iter("node") if n.get("text")=="Ayarlar"),None)
            assert node is not None,"Settings icon not on the first drawer page"
            bounds=tuple(map(int,re.findall(r"\d+",node.get("bounds"))))
            image=Image.open(a.records/(name+".png")).convert("RGB").crop(bounds).resize((100,100))
            fractions[name]=sum(r<60 and g>200 and b>200 for r,g,b in image.getdata())/10000
        assert fractions["icon-pack"]>.05 and fractions["icon-restored"]<.01,fractions
        results["real_icon_pack_and_restore"]=fractions
        shell("pm grant "+PKG+" android.permission.RECORD_AUDIO")
        put("ac_hide_privacy","0");time.sleep(1)
        active=launch("microphone",extras=" --ez secure false --ez microphone true")
        assert active.get("microphone_active") and "error" not in active,active
        green=[]
        for index,hide in enumerate((0,1,0)):
            shell("cmd statusbar collapse");put("ac_hide_privacy",str(hide));time.sleep(2)
            shell("cmd statusbar expand-settings");time.sleep(2);hierarchy("privacy-"+str(index))
            image=Image.open(a.records/("privacy-"+str(index)+".png")).convert("RGB")
            green.append(sum(g>140 and r<100 and b<150 for r,g,b in image.crop((0,0,image.width,500)).getdata()))
        assert green[0]>300 and green[1]<green[0]*.1 and green[2]>300,green
        results["privacy_indicator_live_hide_and_restore"]=green
        shell("am force-stop "+PKG+"; cmd statusbar collapse")
    results={};archive=None;microphone_granted=None
    try:
        assert broker("ping")==b"ArtisanControl/1"
        (a.records/"performance.json").write_bytes(broker("performance"))
        archive=broker("launcher-export");(a.records/"launcher-before.zip").write_bytes(archive)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert json.loads(z.read("artisan-launcher.json"))["package"]=="com.sec.android.app.launcher"
        malformed=io.BytesIO()
        with zipfile.ZipFile(malformed,"w") as z:z.writestr("../outside","rejected")
        try:broker("launcher-import",malformed.getvalue())
        except RuntimeError as e:assert "Invalid archive path" in str(e)
        else:raise AssertionError("Traversal archive was accepted")
        assert broker("ping")==b"ArtisanControl/1"
        results["broker_peer_and_archive_protocol"]=True
        ensure_installed(a.probe,PKG);shell("pm grant "+PKG+" android.permission.POST_NOTIFICATIONS")
        if a.launcher_ui or a.icon_pack: shell("settings put system screen_off_timeout 600000")
        if a.icon_pack:microphone_granted="android.permission.RECORD_AUDIO: granted=true" in shell("dumpsys package "+PKG)
        shell("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard")
        if a.launcher_ui or a.icon_pack:hierarchy("awake")
        for key in KEYS:put(key,"{}" if key=="ac_device_profiles" else "" if key.endswith(("_apps","_packages","_grid")) or key=="ac_icon_pack" else "0")
        put("ac_enabled","1")
        baseline=launch("baseline")
        assert "error" not in baseline,baseline
        assert all(baseline[key] for key in ("control_package_visible","control_listed","control_uid_listed","control_resolved","control_resolved_flags")),baseline
        put("ac_hide_developer_apps",PKG);put("ac_secure_capture_apps",PKG);put("ac_filter_apps",PKG)
        put("ac_hidden_packages","com.android.settings");put("ac_capture_detection_apps",PKG)
        put("ac_device_profiles",json.dumps({PKG:{"MODEL":"ArtisanRegressionModel"}}))
        put("ac_home_enabled","1");put("ac_home_grid","6x9");put("ac_apps_grid","6x9");put("ac_recents_enabled","1");put("ac_recents_layout","2")
        time.sleep(1)
        modified=launch("modified",baseline["control_uid"])
        assert "error" not in modified,modified
        assert modified["developer"]==0 and modified["adb"]==0,modified
        assert modified["model"]=="ArtisanRegressionModel",modified
        assert not any(modified[key] for key in ("control_package_visible","control_listed","control_uid_listed","control_resolved","control_resolved_flags")),modified
        assert modified["home_grid"]==modified["apps_grid"]=="6x9" and modified["recents_enabled"] and modified["recents_layout"]==2,modified
        from PIL import Image
        def orange(file):
            image=Image.open(file).convert("RGB");image=image.crop((0,image.height//5,image.width,image.height*4//5)).resize((100,100))
            return sum(r>220 and 150<g<225 and b<120 for r,g,b in image.getdata())/10000
        before=orange(a.records/"baseline.png");after=orange(a.records/"modified.png")
        assert before<0.05 and after>0.8,(before,after)
        results.update({"secure_surface_captured":True,"developer_hiding_scoped":True,"device_profile_scoped":True,
                        "package_visibility_scoped":True,"native_launcher_models":True,"orange_fraction_before":before,"orange_fraction_after":after})
        if a.launcher_ui:
            put("ac_recents_hide_status","1");put("ac_recents_hide_clear","1")
            launcher_ui()
        if a.icon_pack:icon_and_privacy_ui()
    finally:
        for key,value in saved.items():
            if value=="null":shell("settings delete global "+key)
            else:put(key,value)
        shell("am force-stop "+PKG)
        if microphone_granted is False:shell("pm revoke "+PKG+" android.permission.RECORD_AUDIO")
        if a.launcher_ui or a.icon_pack:
            shell("settings "+("delete system screen_off_timeout" if timeout=="null" else "put system screen_off_timeout "+timeout))
        if archive is not None:
            broker("launcher-import",archive)
            results["launcher_restore_same_version"]=True
        run("forward","--remove","tcp:"+str(port))
        (a.records/"results.json").write_text(json.dumps(results,indent=2))
        (a.records/"control-log.txt").write_text(shell("logcat -d -t 1500 -s ArtisanControl AndroidRuntime"),encoding="utf-8")
    print(json.dumps(results,indent=2))


if __name__=="__main__":main()
