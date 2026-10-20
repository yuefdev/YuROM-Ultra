#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuild owned control DEX and visible branding while preserving donor/hardware payloads."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from build_artisan_control import dex_classes, digest, retain_oem_certificate
from s10_family_fingerprint import VERIFIED_TELEMETRY_OUTPUTS
from s10_settings_branding import build_overlay

BRAND = "YuROM Ultra"
GITHUB = "https://github.com/yuefdev"
VERSION = "v35-test"


def build_bundles(checkout, records):
    output = checkout / "out/host-tools/yurom-settings-v35"
    side_output = checkout / "out/host-tools/yurom-settings-v35-sm-g970f"
    rro = checkout / "out/host-tools/yurom-settings-signature-v35.apk"
    if any(path.exists() for path in (output, side_output, rro)) or not records.is_dir():
        raise ValueError("Fresh versioned outputs and existing external records are required")
    sdk = checkout / "out/host-tools/android-sdk-36"
    tools = sdk / "build-tools/android-16"
    android = sdk / "platform/android-36-ext19/android.jar"
    source = checkout / "packages/ArtisanControl"
    with tempfile.TemporaryDirectory(prefix="yurom-branding-") as directory, (records / "native-build.log").open("xb") as log:
        temporary = Path(directory)
        classes, stubs = temporary / "classes", temporary / "stubs"
        classes.mkdir()
        stubs.mkdir()
        def run(args):
            subprocess.run([str(arg) for arg in args], stdout=log, stderr=subprocess.STDOUT, check=True)
        run(["javac", "--release", "8", "-classpath", android, "-d", stubs, *sorted((source / "stubs").rglob("*.java"))])
        stub_jar = temporary / "stubs.jar"
        with zipfile.ZipFile(stub_jar, "x") as archive:
            for path in stubs.rglob("*.class"):
                archive.write(path, str(path.relative_to(stubs)))
        run(["javac", "--release", "8", "-classpath", str(android) + os.pathsep + str(stubs), "-d", classes, *sorted((source / "src").rglob("*.java"))])
        settings = sorted((classes / "com/android/settings/artisan").rglob("*.class"))
        broker = sorted((classes / "com/artisanrom/control").glob("RootBroker*.class"))
        hooks = sorted(path for path in classes.rglob("*.class") if path not in settings and path not in broker)
        dexes = {}
        for label, selected in (("settings", settings), ("framework", hooks), ("broker", broker)):
            dex = temporary / label
            dex.mkdir()
            run(["java", "-cp", tools / "lib/d8.jar", "com.android.tools.r8.D8", "--min-api", "31", "--lib", android,
                 "--classpath", stub_jar, "--output", dex, *selected])
            dexes[label] = (dex / "classes.dex").read_bytes()
        for suffix, target in (("", output), ("-sm-g970f", side_output)):
            baseline = checkout / ("out/host-tools/artisan-settings-v32" + suffix)
            manifest = json.loads((baseline / "manifest.json").read_text())
            if any(digest(baseline / name) != sha for name, sha in manifest["outputs"].items()):
                raise ValueError("Canonical baseline bundle changed")
            if not suffix and manifest["outputs"] != VERIFIED_TELEMETRY_OUTPUTS:
                raise ValueError("The device-tested V32 broker baseline is required")
            target.mkdir()
            for name in manifest["outputs"]:
                shutil.copy2(baseline / name, target / name)
            for label, prefix in (("settings", "Lcom/android/settings/artisan/"), ("framework", "Lcom/artisanrom/control/")):
                name = label + (".apk" if label == "settings" else ".jar")
                original = baseline / name
                changed = temporary / (label + suffix + ".rebuilt")
                with zipfile.ZipFile(original) as archive:
                    owned = [entry for entry in archive.namelist() if entry.endswith(".dex")
                             and dex_classes(archive.read(entry)) and all(owner.startswith(prefix) for owner in dex_classes(archive.read(entry))) ]
                    if len(owned) != 1:
                        raise ValueError("Expected one isolated owned DEX in " + name)
                    permitted = set(owned)
                    feature_data = None
                    if label == "settings":
                        entry = "assets/artisan/features.json"
                        before_features = json.loads(archive.read(entry))
                        feature_data = (source / "features.json").read_bytes()
                        after_features = json.loads(feature_data)
                        if len(before_features) != len(after_features):
                            raise ValueError("Branding must preserve the feature inventory")
                        for before, after in zip(before_features, after_features):
                            expected = dict(before)
                            expected["label"] = before["label"].replace("Artisan", "YuROM")
                            if expected != after:
                                raise ValueError("A non-label feature contract changed")
                        permitted.add(entry)
                    with zipfile.ZipFile(changed, "x") as rebuilt:
                        for info in archive.infolist():
                            data = dexes[label] if info.filename == owned[0] else feature_data if label == "settings" and info.filename == "assets/artisan/features.json" else archive.read(info.filename)
                            rebuilt.writestr(copy.copy(info), data)
                if label == "settings":
                    aligned = changed.with_suffix(".aligned.apk")
                    run([tools / "zipalign", "-f", "-p", "4", changed, aligned])
                    retain_oem_certificate(original, aligned)
                    run([tools / "zipalign", "-c", "4", aligned])
                    aligned.replace(changed)
                with zipfile.ZipFile(original) as before, zipfile.ZipFile(changed) as after:
                    if before.namelist() != after.namelist() or any(before.read(entry) != after.read(entry) for entry in before.namelist() if entry not in permitted):
                        raise ValueError("An unrelated donor entry changed")
                shutil.copyfile(changed, target / name)
            with zipfile.ZipFile(target / "ArtisanControlBroker.jar", "w") as archive:
                archive.writestr("classes.dex", dexes["broker"], compress_type=zipfile.ZIP_STORED)
            manifest["brand_derivation"] = {"parent_outputs": manifest["outputs"], "brand": BRAND, "github": GITHUB,
                "changed_owned_dex_only": ["settings.apk", "framework.jar", "ArtisanControlBroker.jar"],
                "owned_feature_asset_changes": "visible Artisan labels replaced with YuROM; all keys, defaults and operations unchanged",
                "oem_resources_and_signing_identity_preserved": True, "ce_services_byte_identical": True,
                "compatibility_ids_and_backup_schema_preserved": True}
            manifest["outputs"] = {name: digest(target / name) for name in manifest["outputs"]}
            (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    original = checkout / "out/candidates/oneui9-s10-v18-media-compat/tree/system"
    rro_proof = build_overlay(checkout, original / "priv-app/SecSettings/SecSettings.apk", original / "framework/framework-res.apk", rro)
    (records / "signature-build.json").write_text(json.dumps(rro_proof, indent=2) + "\n")
    return {"bundles": [output.name, side_output.name], "signature": rro.name}


def configure(system, model, signature):
    changed = []
    donor = {}
    for relative in ("build.prop", "product/etc/build.prop", "system_ext/etc/build.prop"):
        path = system / relative
        text = path.read_text()
        donor[relative] = [line for line in text.splitlines() if line.startswith("ro.xgsi.")]
        if "ro.build.display.id=" in text:
            lines = []
            for line in text.splitlines():
                if line.startswith("ro.build.display.id="):
                    if not line.endswith(".XGSI"):
                        raise ValueError("Unknown visible donor build identity")
                    line = line.removesuffix(".XGSI") + ".YuROM_Ultra_V35"
                lines.append(line)
            text = "\n".join(lines) + "\n"
        if relative == "build.prop":
            text += "\n# YuROM public project identity\nro.yurom.name=" + BRAND + "\nro.yurom.version=" + VERSION + "\nro.yurom.github=" + GITHUB + "\n"
        if path.read_text() != text:
            temporary = path.with_name(path.name + ".yurom-new")
            if temporary.exists():
                raise ValueError("Pending property update exists")
            shutil.copy2(path, temporary)
            temporary.write_text(text)
            temporary.replace(path)
            changed.append(relative)
    metadata = {"schema": 1, "name": BRAND, "version": VERSION, "github": GITHUB, "model": model,
        "upstream_donor": {"project": "XGSI", "build": "S942BXXU4ZZH6", "original_properties": donor},
        "upstream_kernel_identity_retained": True, "compatibility_package_ids_retained": True}
    target = system / "etc/yurom-brand.json"
    if target.exists():
        raise ValueError("Preserve the existing brand record")
    target.write_text(json.dumps(metadata, indent=2) + "\n")
    os.chown(target, 0, 0)
    os.chmod(target, 0o644)
    os.setxattr(target, "security.selinux", os.getxattr(system / "etc/floating_feature.xml", "security.selinux"))
    overlay = system / "system_ext/overlay/S10SettingsSignature.apk"
    if not signature.is_file() or not overlay.is_file():
        raise ValueError("The rebuilt YuROM signature and original overlay target are required")
    temporary = overlay.with_name(overlay.name + ".yurom-new")
    shutil.copy2(overlay, temporary)
    temporary.write_bytes(signature.read_bytes())
    temporary.replace(overlay)
    return {**metadata, "signature_sha256": digest(overlay),
            "files": changed + ["etc/yurom-brand.json", "system_ext/overlay/S10SettingsSignature.apk"]}
