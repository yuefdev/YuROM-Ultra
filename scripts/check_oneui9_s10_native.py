#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory native dependencies and the selected audio migration without flashing."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from elftools.elf.elffile import ELFFile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--apex-cache", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if not args.records.is_dir() or args.records.resolve().is_relative_to(checkout):
        parser.error("An existing external records directory is required")
    if args.apex_cache.exists() or not args.apex_cache.parent.is_dir():
        parser.error("A fresh APEX cache under an existing parent is required")
    candidate = json.loads((args.candidate / "input.json").read_text())
    system = args.candidate / "tree/system"
    vendor = args.candidate / "vendor"
    roots = [("/vendor", vendor), ("/system", system), ("/system_ext", system / "system_ext"), ("/product", system / "product")]
    args.apex_cache.mkdir()
    apex_manifest = {}
    for name in ("com.android.vndk.v31", "com.android.runtime", "com.android.i18n", "com.android.art", "com.android.tethering"):
        archives = [path for path in (system / "apex").iterdir() if path.name in (name + ".apex", name + ".capex")]
        if len(archives) != 1:
            raise RuntimeError(f"Expected one native provider APEX: {name}")
        source = archives[0]
        destination = args.apex_cache / name
        destination.mkdir()
        payload = destination / "apex_payload.img"
        with zipfile.ZipFile(source) as archive:
            if "original_apex" in archive.namelist():
                original = destination / "original.apex"
                with archive.open("original_apex") as stream, original.open("xb") as output:
                    shutil.copyfileobj(stream, output, 4 * 1024 * 1024)
                inner = zipfile.ZipFile(original)
            else:
                inner = archive
            try:
                with inner.open("apex_payload.img") as stream, payload.open("xb") as output:
                    shutil.copyfileobj(stream, output, 4 * 1024 * 1024)
            finally:
                if inner is not archive:
                    inner.close()
        mount = destination / "mount"
        mount.mkdir()
        with payload.open("rb") as stream:
            stream.seek(1080)
            ext4 = stream.read(2) == b"\x53\xef"
        subprocess.run(["mount", "-t", "ext4" if ext4 else "erofs", "-o", "loop,ro,noload" if ext4 else "loop,ro",
                        str(payload), str(mount)], check=True)
        try:
            subprocess.run(["cp", "-a", str(mount), str(destination / "tree")], check=True)
        finally:
            subprocess.run(["umount", str(mount)], check=True)
        roots.append(("/apex/" + name, destination / "tree"))
        apex_manifest[name] = {"archive_sha256": digest(source), "payload_sha256": digest(payload)}
    with (args.apex_cache / "input.json").open("x") as stream:
        json.dump(apex_manifest, stream, indent=2)
        stream.write("\n")
    metadata = {}

    def resolve(path):
        seen = set()
        while path.is_symlink():
            if path in seen:
                return None
            seen.add(path)
            target = os.readlink(path)
            if target.startswith("/"):
                matches = [(prefix, root) for prefix, root in roots if target.startswith(prefix + "/")]
                if not matches:
                    return None
                prefix, root = max(matches, key=lambda item: len(item[0]))
                path = root / target[len(prefix):].lstrip("/")
            else:
                path = path.parent / target
        return path if path.is_file() else None

    def inspect(path):
        path = resolve(path)
        if path is None:
            return None
        if path in metadata:
            return metadata[path]
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                return None
            stream.seek(0)
            elf = ELFFile(stream)
            dynamic = elf.get_section_by_name(".dynamic")
            needed = [tag.needed for tag in dynamic.iter_tags() if tag.entry.d_tag == "DT_NEEDED"] if dynamic else []
            symbols = elf.get_section_by_name(".dynsym")
            imports, exports = set(), set()
            if symbols:
                for symbol in symbols.iter_symbols():
                    if not symbol.name:
                        continue
                    if symbol.entry.st_shndx == "SHN_UNDEF":
                        if symbol.entry.st_info.bind != "STB_WEAK":
                            imports.add(symbol.name)
                    elif symbol.entry.st_info.bind in ("STB_GLOBAL", "STB_WEAK") and symbol.entry.st_other.visibility in ("STV_DEFAULT", "STV_PROTECTED"):
                        exports.add(symbol.name)
            result = {"path": path, "bits": elf.elfclass, "needed": needed, "imports": imports, "exports": exports}
        metadata[path] = result
        return result

    providers = defaultdict(list)
    for unused, root in roots:
        for arch in ("lib", "lib64"):
            for path in sorted((root / arch).rglob("*.so")):
                info = inspect(path)
                if info:
                    providers[(info["bits"], path.name)].append(info)

    def provider(consumer, name, bits):
        legacy = consumer["path"].is_relative_to(vendor) or "com.android.vndk.v31" in consumer["path"].parts
        options = providers.get((bits, name), [])
        if not legacy:
            options = [item for item in options if not item["path"].is_relative_to(vendor) and "com.android.vndk.v31" not in item["path"].parts]
        def priority(item):
            path = item["path"]
            if legacy:
                return (0 if path.is_relative_to(vendor) else 1 if "com.android.vndk.v31" in path.parts else
                        2 if "com.android.runtime" in path.parts else 3, str(path))
            return (0 if path.parent == consumer["path"].parent else 1 if path.is_relative_to(system) else 2, str(path))
        return min(options, key=priority) if options else None

    paths = [path for path in (vendor / "bin").rglob("*") if not path.is_dir()]
    paths += [vendor / relative for relative in candidate["audio_interface_migration"]["copied_inputs"]]
    findings, unique = [], set()
    for path in paths:
        entry = inspect(path)
        if entry is None or entry["path"] in unique:
            continue
        unique.add(entry["path"])
        queue, seen, loaded, missing = [entry], set(), [], set()
        while queue:
            current = queue.pop()
            if current["path"] in seen:
                continue
            seen.add(current["path"])
            loaded.append(current)
            for name in current["needed"]:
                value = provider(current, name, entry["bits"])
                if value is None:
                    missing.add(name)
                else:
                    queue.append(value)
        exports = set().union(*(item["exports"] for item in loaded))
        unresolved = sorted(set().union(*(item["imports"] for item in loaded)) - exports) if not missing else []
        if missing or unresolved:
            findings.append({"entry": str(path.relative_to(vendor)), "bits": entry["bits"],
                             "missing_libraries": sorted(missing), "tentative_unresolved_symbols": unresolved})
    manifest = ET.parse(vendor / "etc/vintf/manifest.xml").getroot()
    audio_versions = {hal.findtext("name"): hal.findtext("version") for hal in manifest.findall("hal")
                      if hal.findtext("name") in ("android.hardware.audio", "android.hardware.audio.effect")}
    art32 = (args.apex_cache / "com.android.art/tree/lib/libart.so").is_file()
    report = {"scope": "vendor executables and migrated audio libraries; selected native APEX providers",
              "unique_elf_entries_checked": len(unique), "findings": findings, "art_32bit_present": art32,
              "audio_hal_versions": audio_versions, "audio_hidl_6_platform_client_present": (system / "lib64/libaudiohal@6.0.so").is_file(),
              "linker_namespaces_checked": False, "symbol_versions_checked": False,
              "hidl_registration_runtime_checked": False, "device_boot_tested": False}
    with (args.records / "native-check.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key != "findings"}, indent=2))
    print(f"Native dependency findings: {len(findings)}")
    if findings or not art32 or set(audio_versions.values()) != {"6.0"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
