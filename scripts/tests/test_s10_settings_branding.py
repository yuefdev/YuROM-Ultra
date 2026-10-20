#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the compiled RRO against the real donor preference contract."""

import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import zipfile


def xmltree(tool, apk, resource):
    text = subprocess.check_output([str(tool), "dump", "xmltree", "--file", resource, str(apk)], text=True)
    stack = []
    root = None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        element = re.match(r"\s*E: (\S+) \(line=", line)
        if element:
            node = {"tag": element[1], "attributes": {}, "children": []}
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                stack[-1][1]["children"].append(node)
            else:
                root = node
            stack.append((indent, node))
        elif line.lstrip().startswith("A:") and stack:
            attribute = re.match(r"\s*A: .*?\((0x[0-9a-f]+)\)=(.*)", line)
            if attribute:
                stack[-1][1]["attributes"][attribute[1]] = attribute[2]
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--original-settings", type=Path, help="Pinned original when the optional native control fragment changes Settings DEX")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("branding", checkout / "scripts/s10_settings_branding.py")
    branding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(branding)
    tool = checkout / "out/host-tools/android-sdk-36/build-tools/android-16/aapt2"
    settings = args.system / "priv-app/SecSettings/SecSettings.apk"
    overlay = args.system / "system_ext/overlay/S10SettingsSignature.apk"
    reference = args.original_settings or settings
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == "57792a331109cc889d8d2be0caa8d0d4e40ade53fc1e0c608e96c582b0d20b35"
    if args.original_settings:
        with zipfile.ZipFile(reference) as original, zipfile.ZipFile(settings) as native:
            for name in original.namelist():
                if not re.fullmatch(r"classes\d*\.dex", name):assert native.read(name) == original.read(name), name
    resource = "res/xml/sec_software_info_settings.xml"
    before = xmltree(tool, settings, resource)
    after = xmltree(tool, overlay, resource)
    category = after["children"][0]
    assert category["attributes"].pop("0x010100f2").startswith("@0x7f")
    assert category["attributes"].pop("0x010101ee") == "false"
    assert category["attributes"]["0x010101e1"].startswith("@0x7f")
    category["attributes"]["0x010101e1"] = before["children"][0]["attributes"]["0x010101e1"]
    # External Settings IDs use AAPT's named dynamic-library slot 0x02. At
    # runtime AssetManager resolves it to the target's 0x7f, distinct from the RRO.
    def normalize(node):
        node["attributes"] = {key.replace("0x02", "0x7f", 1): value.replace("@0x02", "@0x7f")
                              for key, value in node["attributes"].items()}
        for child in node["children"]:
            normalize(child)
    normalize(after)
    github = [node for node in category["children"] if node["attributes"].get("0x010101e8", "").startswith('"yurom_github"')]
    assert len(github) == 1 and github[0]["children"][0]["tag"] == "intent"
    link = github[0]["children"][0]["attributes"]
    assert link["0x0101002d"].startswith('"android.intent.action.VIEW"') and link["0x0101002e"].startswith('"https://github.com/yuefdev"')
    category["children"].remove(github[0])
    assert after == before, "An original preference, resource reference or controller changed"
    assert len(category["children"]) == 13
    allowlist = (args.system / "etc/sysconfig/allowed-system-preload-apps.xml").read_bytes()
    assert allowlist.count(branding.ALLOWLIST_ENTRY) == 1
    original = allowlist.replace(branding.ALLOWLIST_ENTRY, b"")
    assert hashlib.sha256(original).hexdigest() == branding.ALLOWLIST_SHA256

    def resources(apk):
        text = subprocess.check_output([str(tool), "dump", "resources", str(apk)], text=True)
        return set(re.findall(r"resource 0x[0-9a-f]+ ([^\s]+)", text))

    assert resources(settings) & resources(overlay) == {"xml/sec_software_info_settings"}
    with zipfile.ZipFile(overlay) as archive:
        assert not any(n.endswith(".dex") or n.startswith("lib/") for n in archive.namelist())
        frames = [n for n in archive.namelist()
                  if re.fullmatch(r"res/drawable-nodpi(?:-v\d+)?/s10_blackhole_\d{2}\.webp", n)]
        assert len(frames) == 36, "The complete native black-hole animation must ship in the overlay"
    layout = xmltree(tool, overlay, "res/layout/s10_signature_card.xml")
    assert layout["tag"] == "FrameLayout"
    print("PASS: YuROM signature and exact HTTPS GitHub intent; all 13 original preferences and controllers survive.")
    print("PASS: relocatable overlay references, code-free APK and isolated resource mapping.")
    print("PASS: preload allowlist adds only this package and preserves all original bytes and notices.")
    print("PASS: 36 offline-rendered frames ship without executable code or a network dependency.")


if __name__ == "__main__":
    main()
