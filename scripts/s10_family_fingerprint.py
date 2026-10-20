#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt a pinned native Artisan bundle to the S10e's original side sensor."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from build_artisan_control import dex_classes, retain_oem_certificate
from s10_models import ROOT, digest

BASELINE_OUTPUTS = {
    "services.jar": "3740c04896ec8f39b29b0dd911da30687a5570aa75e5916ee52f5e8596be5a35",
    "framework.jar": "7f7209823b313fb1edfd69c2dcdccc67a871c6b6db2d537943de60c7f6bd9b05",
    "home.apk": "f67f2b17fe7edd69ff069c2d6e65ca7503ab2a88e2e8519d6df2fe703fb9b596",
    "systemui.apk": "eced1af545ab42d51a668564e10ffb9169377eab5c0605d860697ddd658635cf",
    "settings.apk": "22569bad85ee4490e2b7e8e83c410976f7bbc74e00dab586cae66b304c4b6601",
    "ArtisanControlBroker.jar": "270e22f571630a06de87db8efcd766041d31c50bcee2086d3d9a77f98ebb3e59",
}
OC_OUTPUTS = dict(BASELINE_OUTPUTS, **{
    "settings.apk": "f006c991e0589bed43fecdffa5026cda59beb11b65555229880e53b3c18c1968",
    "ArtisanControlBroker.jar": "e362f6420c738385c2ab738cd37548ddde5441da8430bbb92bd5ed220566de06",
})
PERSISTENT_OC_OUTPUTS = dict(BASELINE_OUTPUTS, **{
    "settings.apk": "f5433cbd271ec2133cdfe715a5f3110f5039890a8c5924e168ea43983efabf9f",
    "ArtisanControlBroker.jar": "a1b2f40ddb4e2ccd0634e26ab178a74dfed1517dcaf50ae6c1d036b7f8b7ae5a",
})
TELEMETRY_OUTPUTS = dict(BASELINE_OUTPUTS, **{
    "settings.apk": "71b31247717e62b7576f6ba9ce7a8de05dbcfb7cd010ed84dec6c79d2d825c84",
    "ArtisanControlBroker.jar": "f19ccc4f4c40e28160d24b5dda32c35ffdbe6c3f3635130290613e17aa9e945a",
})
VERIFIED_TELEMETRY_OUTPUTS = dict(TELEMETRY_OUTPUTS, **{
    "ArtisanControlBroker.jar": "482255c9566c1d992ce3d5185464fcaec79b29dfe3df4320df54e9073c07f827",
})
SIDE_CONFIG = "google_touch_side,navi=1"


def edit_sensor_class(owner, text):
    if owner == "Lcom/android/server/biometrics/SemBiometricFeature;":
        edits = [("sput-boolean v2, " + owner + "->" + field + ":Z",
                  "sput-boolean v3, " + owner + "->" + field + ":Z")
                 for field in ("FP_FEATURE_SENSOR_IS_IN_DISPLAY_TYPE", "FP_FEATURE_SENSOR_IS_ULTRASONIC")]
        if "const/4 v3, 0x0" not in text or "const/4 v2, 0x1" not in text:
            raise ValueError("Unknown biometric feature register contract")
    elif owner == "Lcom/android/systemui/LsRune;":
        edits = [("sput-boolean v3, " + owner + "->SECURITY_FINGERPRINT_IN_DISPLAY:Z",
                  "sput-boolean v2, " + owner + "->SECURITY_FINGERPRINT_IN_DISPLAY:Z")]
        if "const/4 v2, 0x0" not in text or "const/4 v3, 0x1" not in text:
            raise ValueError("Unknown lock-screen feature register contract")
    elif owner == "Lcom/samsung/android/bio/fingerprint/SemFingerprintManager;":
        old = '"google_touch_display_ultrasonic"'
        if text.count(old) != 2:
            raise ValueError("Unknown fingerprint product feature contract")
        return text.replace(old, '"' + SIDE_CONFIG + '"')
    else:
        raise ValueError("Unregistered sensor class")
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError("The pinned fingerprint assignment changed")
        text = text.replace(before, after)
    return text


def build(baseline, output, records, build_tools):
    if output.exists() or not output.parent.is_dir() or not records.is_dir() or records.resolve().is_relative_to(ROOT):
        raise ValueError("New bundle output and existing external records are required")
    if (records / "side-sensor-build.log").exists():
        raise ValueError("Use fresh external records for this bundle build")
    manifest = json.loads((baseline / "manifest.json").read_text())
    outputs = manifest["outputs"]
    if outputs not in (BASELINE_OUTPUTS, OC_OUTPUTS, PERSISTENT_OC_OUTPUTS, TELEMETRY_OUTPUTS, VERIFIED_TELEMETRY_OUTPUTS) or any(digest(baseline / name) != expected for name, expected in outputs.items()):
        raise ValueError("A registered native Artisan baseline is required")
    output.mkdir()
    for name in BASELINE_OUTPUTS:
        shutil.copyfile(baseline / name, output / name)
    changes = {"services.jar": "Lcom/android/server/biometrics/SemBiometricFeature;",
               "framework.jar": "Lcom/samsung/android/bio/fingerprint/SemFingerprintManager;",
               "systemui.apk": "Lcom/android/systemui/LsRune;"}
    proof = []
    with (records / "side-sensor-build.log").open("xb") as log, tempfile.TemporaryDirectory(prefix="s10-side-sensor-") as temporary:
        temp = Path(temporary)
        for name, owner in changes.items():
            original = baseline / name
            with zipfile.ZipFile(original) as source:
                entries = [entry for entry in source.namelist() if re.fullmatch(r"classes\d*\.dex", entry)
                           and owner in dex_classes(source.read(entry))]
                if len(entries) != 1:
                    raise ValueError("Missing or duplicate fingerprint feature owner: " + name)
                entry = entries[0]
                folder = temp / name
                subprocess.run(["baksmali", "d", "--debug-info", "false", "-l", "-j", "8", "-o", str(folder),
                                str(original) + "/" + entry], stdout=log, stderr=subprocess.STDOUT, check=True)
                path = folder / (owner[1:-1] + ".smali")
                before = path.read_text()
                path.write_text(edit_sensor_class(owner, before))
                # The original valid credential flow and V23 CE sentinel remain in the same services DEX.
                if name == "services.jar":
                    ce = folder / "com/android/server/StorageManagerService$StorageManagerInternalImpl.smali"
                    if 'const-string p2, "!"' not in ce.read_text():
                        raise ValueError("The V23 tokenless-CE fix is missing")
                dex = temp / (name + ".dex")
                subprocess.run(["smali", "a", "-a", "35", "-j", "8", "-o", str(dex), str(folder)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
                if set(dex_classes(dex.read_bytes())) != set(dex_classes(source.read(entry))):
                    raise ValueError("Fingerprint adaptation changed the class inventory")
                target = output / name
                with zipfile.ZipFile(target, "w") as packed:
                    for item in source.infolist():
                        packed.writestr(copy.copy(item), dex.read_bytes() if item.filename == entry else source.read(item.filename))
                if name.endswith(".apk"):
                    aligned = temp / "aligned.apk"
                    subprocess.run([str(build_tools / "zipalign"), "-f", "-p", "4", str(target), str(aligned)], check=True)
                    shutil.copyfile(aligned, target)
                    retain_oem_certificate(original, target)
                with zipfile.ZipFile(target) as packed:
                    for unchanged in source.namelist():
                        if unchanged != entry and source.read(unchanged) != packed.read(unchanged):
                            raise ValueError("An unrelated fingerprint archive payload changed")
                proof.append({"file": name, "dex": entry, "class": owner, "original_sha256": digest(original), "sha256": digest(target)})
    manifest["outputs"] = {name: digest(output / name) for name in BASELINE_OUTPUTS}
    manifest["model_adaptation"] = {"model": "SM-G970F", "sensor": SIDE_CONFIG, "changes": proof,
                                    "v23_ce_fix_retained": True, "device_fingerprint_tested": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (records / "side-sensor-build.json").write_text(json.dumps(manifest["model_adaptation"], indent=2) + "\n")
    print(json.dumps(manifest["model_adaptation"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "output", "records", "build-tools"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.baseline, args.output, args.records, args.build_tools)
