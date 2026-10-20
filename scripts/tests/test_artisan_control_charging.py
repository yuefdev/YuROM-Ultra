#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify real charging windows, live positioning and animation expiry on a root device."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from PIL import Image,ImageChops


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb",type=Path,required=True);p.add_argument("--serial",required=True)
    p.add_argument("--records",type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if a.records.exists() or not a.records.parent.is_dir() or a.records.resolve().is_relative_to(root):p.error("New external records directory required")
    a.records.mkdir();adb=[str(a.adb),"-s",a.serial]
    def run(*args):return subprocess.run([*adb,*args],check=True,capture_output=True,timeout=60).stdout
    def sh(command):return run("shell",command).decode(errors="replace").strip()
    if sh("id -u")!="0":raise RuntimeError("Root ADB is required")
    battery=sh("dumpsys battery")
    if "UPDATES STOPPED" in battery:raise RuntimeError("An existing battery simulation must be restored before this test")
    def put(key,value):sh("settings put global "+key+" '"+str(value).replace("'","'\\''")+"'")
    def windows(name):
        data=sh("dumpsys window windows");(a.records/(name+".txt")).write_text(data,encoding="utf-8")
        return [block for block in re.split(r"(?=  Window #\d+ )",data)
                if re.match(r"  Window #\d+ Window\{[^\n]*ArtisanControl charging\}:",block)]
    def bottom(blocks):
        for block in blocks:
            match=re.search(r"mAttrs=\{\(0,(\d+)\)\(fillx\d+\)",block)
            if match:return int(match[1])
    def art(blocks):return any("(fillxfill)" in block and "mHasSurface=true" in block for block in blocks)
    def shot(name):
        path=a.records/(name+".png");path.write_bytes(run("exec-out","screencap","-p"))
        return Image.open(path).convert("RGB")
    keys=("ac_enabled","ac_charge_info","ac_charge_interval","ac_charge_bottom","ac_charge_animation","ac_charge_animation_seconds")
    before={key:sh("settings get global "+key) for key in keys};timeout=sh("settings get system screen_off_timeout");results={}
    (a.records/"settings-before.json").write_text(json.dumps(before,indent=2))
    (a.records/"battery-before.txt").write_text(battery)
    try:
        sh("settings put system screen_off_timeout 600000")
        for key,value in {"ac_enabled":1,"ac_charge_info":1,"ac_charge_interval":500,"ac_charge_bottom":100,"ac_charge_animation":0}.items():put(key,value)
        sh("input keyevent KEYCODE_SLEEP");time.sleep(.5);sh("input keyevent KEYCODE_WAKEUP");time.sleep(1.2)
        first=bottom(windows("info-position-100"));shot("info-100")
        put("ac_charge_bottom",180);time.sleep(1.5);second=bottom(windows("info-position-180"));shot("info-180")
        results["charge_info_visible"]=first is not None
        results["live_bottom_position"]={"before":first,"after":second,"pass":first is not None and second is not None and second>first+100}
        put("ac_charge_info",0);put("ac_charge_interval",30000)
        for style,name in ((1,"flow"),(2,"wave")):
            put("ac_charge_animation",style);put("ac_charge_animation_seconds",15)
            sh("dumpsys battery set usb 0");time.sleep(.5);sh("dumpsys battery set usb 1")
            time.sleep(.65);active=art(windows(name+"-active"))
            first_frame=shot(name+"-1");time.sleep(.2);second_frame=shot(name+"-2")
            region=(0,first_frame.height*2//5,first_frame.width,first_frame.height*92//100)
            changed=ImageChops.difference(first_frame.crop(region),second_frame.crop(region)).getbbox() is not None
            put("ac_charge_animation_seconds",2);sh("dumpsys battery set usb 0");time.sleep(.5);sh("dumpsys battery set usb 1")
            start=time.monotonic();time.sleep(.65);short_active=art(windows(name+"-short-active"))
            time.sleep(max(0,3.5-(time.monotonic()-start)));expired=not art(windows(name+"-expired"))
            results[name]={"window_visible":active,"frames_differ":changed,"short_animation_visible":short_active,"expires_with_long_information_interval":expired}
        sh("input keyevent KEYCODE_SLEEP")
        for attempt in range(20):
            time.sleep(.25)
            if not windows("screen-off"):break
        results["screen_off_removes_charge_windows"]=not windows("screen-off")
    finally:
        sh("dumpsys battery reset")
        for key,value in before.items():
            if value=="null":sh("settings delete global "+key)
            else:put(key,value)
        sh("settings "+("delete system screen_off_timeout" if timeout=="null" else "put system screen_off_timeout "+timeout))
        sh("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard")
        (a.records/"results.json").write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
    assert results["charge_info_visible"] and results["live_bottom_position"]["pass"]
    assert all(results[name]["window_visible"] and results[name]["frames_differ"] and results[name]["short_animation_visible"] and results[name]["expires_with_long_information_interval"] for name in ("flow","wave"))
    assert results["screen_off_removes_charge_windows"]


if __name__=="__main__":main()
