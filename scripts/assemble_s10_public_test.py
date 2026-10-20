#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble immutable per-model public-test payloads, launchers and honest acceptance metadata."""
import argparse
import json
import os
from pathlib import Path
import re

from s10_models import ROOT, digest


def assemble(version, output, records, acceptance):
    if (not re.fullmatch(r"v[0-9]+-(?:test|beta)", version) or output.exists() or not output.parent.is_dir()
            or not records.is_dir() or records.resolve().is_relative_to(ROOT) or not acceptance.is_file()):
        raise ValueError("A versioned release output, existing parent and external acceptance record are required")
    tag = version.removesuffix("-test")
    channel = "beta" if version.endswith("-beta") else "public-test"
    device = json.loads(acceptance.read_text())
    if device.get("version") != version or device.get("model") != "SM-G973F":
        raise ValueError("Matching versioned physical S10 acceptance is required")
    profiles = json.loads((ROOT / "target/beyond1lte/oneui9/display/profiles.json").read_text())["models"]
    rows = []
    for model in ("SM-G970F", "SM-G973F", "SM-G975F"):
        model_records = records / model / tag
        package = json.loads((model_records / "package.json").read_text())
        bootstrap = json.loads((model_records / "bootstrap-package.json").read_text())
        assert package["model"] == bootstrap["model"] == model and package["version"] == bootstrap["version"] == version
        assert package["packed_image_chunks_verified"] == 11 and package["clean_install_required"] and not package["repartition"]
        assert bootstrap["payload_sha256"] == package["zip_sha256"] and bootstrap["legacy_ufs_alias_supported"]
        assert bootstrap["recovery_shell"] == "busybox-sh" and bootstrap["original_installer_checks_preserved"]
        files = []
        for name, size, sha in ((package["zip_file"], package["zip_bytes"], package["zip_sha256"]),
                                (bootstrap["launcher_file"], bootstrap["launcher_bytes"], bootstrap["launcher_sha256"])):
            source = ROOT / "out" / name
            assert source.is_file() and source.stat().st_size == size
            assert source.with_suffix(source.suffix + ".sha256").read_text().split()[0] == sha
            assert digest(source) == sha
            files.append({"name": name, "bytes": size, "sha256": sha})
        rows.append({"model": model, "version": version, "rom": package["rom"], "files": files, "display_profile": profiles[model],
                     "host_image_and_chunk_gates": "passed", "physical_acceptance": device if model == "SM-G973F" else {
                         "model": model, "device_tested": False, "status": "pending physical boot/camera/fingerprint/panel/radio testing"}})
    text = (ROOT / "target/beyond1lte/oneui9/installer/RELEASE_TR.md").read_text().replace("{{VERSION}}", version)
    output.mkdir()
    checksums = []
    for row in rows:
        folder = output / row["model"]
        folder.mkdir()
        for item in row["files"]:
            source = ROOT / "out" / item["name"]
            target = folder / item["name"]
            os.link(source, target)
            assert source.stat().st_ino == target.stat().st_ino and source.stat().st_dev == target.stat().st_dev
            checksum = item["sha256"] + "  " + item["name"] + "\n"
            target.with_suffix(target.suffix + ".sha256").write_text(checksum)
            checksums.append(item["sha256"] + "  " + row["model"] + "/" + item["name"])
        (folder / "SHA256SUMS.txt").write_text("".join(item["sha256"] + "  " + item["name"] + "\n" for item in row["files"]))
        (folder / "VALIDATION.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n")
        launcher = next(item["name"] for item in row["files"] if "_INSTALLER_" in item["name"])
        payload = next(item["name"] for item in row["files"] if item["name"].endswith("_TWRP.zip"))
        preface = "# Bu klasör yalnızca " + row["model"] + " içindir\n\n"
        preface += "Aynı klasörde bulunması gereken dosyalar:\n- `" + payload + "`\n- `" + launcher + "`\n\n"
        preface += "TWRP'de küçük `" + launcher + "` dosyasını seçin.\n\n"
        (folder / "KURULUM_TR.md").write_text(preface + text)
    (output / "KURULUM_TR.md").write_text(text)
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    (output / "RELEASE.json").write_text(json.dumps({"rom": rows[0]["rom"], "version": version, "channel": channel, "models": rows,
         "selinux_enforcing_accepted": False, "unverified_models_not_claimed_tested": True}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"directory": output.name, "model_count": len(rows), "zip_count": 6, "channel": channel}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    for name in ("output", "records", "acceptance"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    assemble(args.version, args.output, args.records, args.acceptance)
