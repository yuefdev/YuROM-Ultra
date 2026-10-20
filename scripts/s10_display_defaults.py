#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package the reviewed S10 camera inset and first-install native FHD preference."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

SOURCE = "scripts/android/S10DisplayOverlay.java"
FILES = {"s10-display-defaults.jar": "framework/s10-display-defaults.jar",
         "s10-display-defaults.sh": "etc/s10-display-defaults.sh", "s10-display-defaults.rc": "etc/init/s10-display-defaults.rc",
         "s10-display-defaults.json": "etc/s10-display-defaults.json"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(checkout, output):
    source = checkout / SOURCE
    resources = checkout / "target/beyond1lte/oneui9/display"
    inputs = {SOURCE: digest(source), **{str(path.relative_to(checkout)): digest(path) for path in sorted(resources.iterdir())}}
    manifest = output / "manifest.json"
    if output.exists():
        metadata = json.loads(manifest.read_text())
        if metadata["inputs"] != inputs or any(digest(output / name) != sha for name, sha in metadata["outputs"].items()):
            raise ValueError("Display defaults output differs; use a fresh versioned bundle")
        return metadata
    if not output.parent.is_dir():
        raise ValueError("An existing output parent is required")
    sdk = checkout / "out/host-tools/android-sdk-36"
    android = sdk / "platform/android-36-ext19/android.jar"
    d8 = sdk / "build-tools/android-16/lib/d8.jar"
    with tempfile.TemporaryDirectory(prefix="s10-display-defaults-") as temporary:
        temporary = Path(temporary)
        classes, dex = temporary / "classes", temporary / "dex"
        classes.mkdir()
        dex.mkdir()
        subprocess.run(["javac", "--release", "8", "-classpath", str(android), "-d", str(classes), str(source)], check=True)
        subprocess.run(["java", "-cp", str(d8), "com.android.tools.r8.D8", "--min-api", "31", "--lib", str(android),
                        "--output", str(dex), str(classes / "S10DisplayOverlay.class")], check=True)
        output.mkdir()
        with zipfile.ZipFile(output / "s10-display-defaults.jar", "x") as archive:
            archive.write(dex / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_STORED)
        for name in ("s10-display-defaults.sh", "s10-display-defaults.rc"):
            shutil.copyfile(resources / name, output / name)
        shutil.copyfile(resources / "profiles.json", output / "s10-display-defaults.json")
    profiles = json.loads((resources / "profiles.json").read_text())["models"]
    metadata = {"schema": 1, "models": profiles, "inputs": inputs, "outputs": {name: digest(output / name) for name in FILES},
                "preserves_subsequent_user_preferences": True}
    manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def configure(checkout, system, model):
    bundle = checkout / "out/host-tools/s10-display-defaults-v2"
    metadata = build(checkout, bundle)
    if model not in metadata["models"]:
        raise ValueError("No reviewed display geometry for this model")
    references = {"framework": system / "framework/framework.jar", "etc": system / "etc/floating_feature.xml",
                  "init": system / "etc/init/artisan-control.rc"}
    for name, relative in FILES.items():
        path = system / relative
        if path.exists():
            raise ValueError("Display defaults already staged; preserve the existing candidate")
        reference = references["framework" if relative.startswith("framework/") else "init" if relative.startswith("etc/init/") else "etc"]
        shutil.copyfile(bundle / name, path)
        os.chown(path, 0, 0)
        os.chmod(path, 0o644)
        os.setxattr(path, "security.selinux", os.getxattr(reference, "security.selinux"))
    profile = metadata["models"][model]
    return {**metadata, "model": model, "camera_inset_portrait_dp": profile["portrait_indicator_padding_dp"],
            "default_native_mode": profile["default_mode"], "default_density": profile["default_density"], "files": list(FILES.values())}
