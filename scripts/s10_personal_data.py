#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate donor PDE startup on the advertised platform capability before secure storage is used."""
import argparse
import copy
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from build_artisan_control import dex_classes, retain_oem_certificate
from s10_models import ROOT, digest

INPUT_SHA = "6eb64791b4469d3ad490671dc54f14279991e27f62fa0db7088a3bb52b6dac01"
OWNER = "Lcom/samsung/android/moneta/app/MonetaInitializationProvider;"
SEARCH_OWNER = "Lcom/samsung/android/moneta/search/provider/DataProvider;"
FEATURE = "SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_PERSONALIZED_DATA_CORE"


def provider_patch(text):
    before = "    if-eqz v0, :cond_3d\n\n    invoke-virtual {p0}, Landroid/content/ContentProvider;->getContext()Landroid/content/Context;"
    guard = '''    if-eqz v0, :cond_3d

    invoke-static {}, Lcom/samsung/android/feature/SemFloatingFeature;->getInstance()Lcom/samsung/android/feature/SemFloatingFeature;
    move-result-object v0
    const-string v4, "SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_PERSONALIZED_DATA_CORE"
    invoke-virtual {v0, v4}, Lcom/samsung/android/feature/SemFloatingFeature;->getBoolean(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :cond_3d

    invoke-virtual {p0}, Landroid/content/ContentProvider;->getContext()Landroid/content/Context;'''
    message = '"Not Main User, Moneta will be disabled and worker will be canceled."'
    if text.count(before) != 1 or text.count(message) != 1 or text.count("->disableComponents(Landroid/content/Context;)V") != 1:
        raise ValueError("The pinned Moneta capability/lifecycle contract changed")
    return text.replace(before, guard).replace(message, '"PDE unavailable for this user or platform; Moneta components and workers disabled."')


def search_provider_patch(text):
    before = ".method public init()Z\n    .locals 4\n\n    const/4 v0, 0x4"
    guard = '''.method public init()Z
    .locals 4

    invoke-static {}, Lcom/samsung/android/feature/SemFloatingFeature;->getInstance()Lcom/samsung/android/feature/SemFloatingFeature;
    move-result-object v0
    const-string v1, "SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_PERSONALIZED_DATA_CORE"
    invoke-virtual {v0, v1}, Lcom/samsung/android/feature/SemFloatingFeature;->getBoolean(Ljava/lang/String;)Z
    move-result v0
    if-nez v0, :pde_platform_supported
    const-string v0, "Startup"
    const-string v1, "PDE unavailable; search provider warmup skipped."
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    const/4 v0, 0x0
    return v0

    :pde_platform_supported
    const/4 v0, 0x4'''
    if (text.count(before) != 1 or text.count('"DataProvider init (IO warmup scheduled)"') != 1
            or text.count("Lcom/samsung/android/moneta/search/provider/DataProvider$init$1;") < 1):
        raise ValueError("The pinned search-provider startup contract changed")
    return text.replace(before, guard)


def semantics(text):
    # DEX string-index width and code-offset labels can change on reassembly.
    labels = {}
    text = text.replace("const-string/jumbo ", "const-string ")
    return re.sub(r":(?:cond|goto|try_start|try_end|catch|catchall|pswitch|pswitch_data|sswitch|sswitch_data|array)_[0-9a-f]+\b",
                  lambda match: labels.setdefault(match[0], ":label_" + str(len(labels))), text)


def build(apk, output, records, tools):
    if (digest(apk) != INPUT_SHA or output.exists() or not output.parent.is_dir()
            or not records.is_dir() or records.resolve().is_relative_to(ROOT)):
        raise ValueError("Pinned donor APK, new output and existing external records are required")
    with (records / "pde-build.log").open("xb") as log, tempfile.TemporaryDirectory(prefix="s10-pde-") as temporary:
        temp = Path(temporary)
        with zipfile.ZipFile(apk) as original:
            patches = {OWNER: provider_patch, SEARCH_OWNER: search_provider_patch}
            dexes, seen = {}, []
            for name in original.namelist():
                if re.fullmatch(r"classes\d*\.dex", name):
                    owners = [owner for owner in patches if owner in dex_classes(original.read(name))]
                    if owners:
                        dexes[name] = owners
                        seen.extend(owners)
            if sorted(seen) != sorted(patches):
                raise ValueError("Both PDE startup owners must occur exactly once")
            changed_dex, untouched_classes = {}, 0
            for entry, owners in dexes.items():
                workspace = temp / entry
                workspace.mkdir()
                folder, canonical = workspace / "smali", workspace / "canonical"
                subprocess.run(["baksmali", "d", "--debug-info", "false", "-l", "-j", "8", "-o", str(folder), str(apk) + "/" + entry], stdout=log, stderr=subprocess.STDOUT, check=True)
                canonical_dex = workspace / "canonical.dex"
                subprocess.run(["smali", "a", "-a", "35", "-j", "8", "-o", str(canonical_dex), str(folder)], stdout=log, stderr=subprocess.STDOUT, check=True)
                subprocess.run(["baksmali", "d", "--debug-info", "false", "-l", "-j", "8", "-o", str(canonical), str(canonical_dex)], stdout=log, stderr=subprocess.STDOUT, check=True)
                original_classes = {str(p.relative_to(canonical)): p.read_bytes() for p in canonical.rglob("*.smali")}
                changed_paths = {owner[1:-1] + ".smali" for owner in owners}
                for owner in owners:
                    target = folder / (owner[1:-1] + ".smali")
                    target.write_text(patches[owner](target.read_text()))
                dex = workspace / "classes.dex"
                subprocess.run(["smali", "a", "-a", "35", "-j", "8", "-o", str(dex), str(folder)], stdout=log, stderr=subprocess.STDOUT, check=True)
                if set(dex_classes(dex.read_bytes())) != set(dex_classes(original.read(entry))):
                    raise ValueError("PDE class inventory changed")
                rebuilt = workspace / "verify"
                subprocess.run(["baksmali", "d", "--debug-info", "false", "-l", "-j", "8", "-o", str(rebuilt), str(dex)], stdout=log, stderr=subprocess.STDOUT, check=True)
                for name, before in original_classes.items():
                    after = (rebuilt / name).read_text()
                    if name not in changed_paths and semantics(after) != semantics(before.decode()):
                        log.write("".join(difflib.unified_diff(before.decode().splitlines(True), after.splitlines(True), fromfile=name, tofile="rebuilt")).encode())
                        raise ValueError("An unrelated PDE class changed: " + name)
                changed_dex[entry] = dex.read_bytes()
                untouched_classes += len(original_classes) - len(owners)
            raw = temp / "patched.apk"
            with zipfile.ZipFile(raw, "w") as packed:
                for info in original.infolist():
                    packed.writestr(copy.copy(info), changed_dex.get(info.filename, original.read(info.filename)))
            output.mkdir()
            final = output / "SamsungSmartSuggestions.apk"
            subprocess.run([str(tools / "zipalign"), "-f", "-p", "4", str(raw), str(final)], check=True)
            retain_oem_certificate(apk, final)
            with zipfile.ZipFile(final) as packed:
                assert original.namelist() == packed.namelist()
                for name in original.namelist():
                    if name not in changed_dex and original.read(name) != packed.read(name):
                        raise ValueError("An unrelated PDE archive payload changed")
    result = {"schema": 1, "input_sha256": INPUT_SHA, "output_sha256": digest(final), "changed_class": OWNER,
              "changed_classes": [OWNER, SEARCH_OWNER], "search_provider_capability_gate": True,
              "feature": FEATURE, "unsupported_feature_value": "FALSE", "existing_component_disable_path": True,
              "secure_storage_fallback_added": False, "unrelated_classes_verified": untouched_classes,
              "device_crash_retest_passed": False}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    (records / "pde-build.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def configure(system, bundle):
    metadata = json.loads((bundle / "manifest.json").read_text())
    target = system / "priv-app/SamsungSmartSuggestions/SamsungSmartSuggestions.apk"
    if metadata.get("input_sha256") != INPUT_SHA or digest(target) != INPUT_SHA or digest(bundle / target.name) != metadata["output_sha256"]:
        raise ValueError("Unexpected PDE compatibility input")
    floating = system / "etc/floating_feature.xml"
    before = floating.read_text()
    flag = "<" + FEATURE + ">TRUE</" + FEATURE + ">"
    if before.count(flag) != 1:
        raise ValueError("The original donor PDE feature contract changed")
    target.write_bytes((bundle / target.name).read_bytes())
    floating.write_text(before.replace(flag, "<" + FEATURE + ">FALSE</" + FEATURE + ">"))
    return dict(metadata, files={"priv-app/SamsungSmartSuggestions/SamsungSmartSuggestions.apk": digest(target), "etc/floating_feature.xml": digest(floating)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("apk", "output", "records", "build-tools"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.apk, args.output, args.records, args.build_tools)
