#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the portable control app and a checksum-pinned, reversible ROM adapter."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "packages/ArtisanControl"
HOOK = "Lcom/artisanrom/control/"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dex_classes(data):
    count, start = struct.unpack_from("<II", data, 56)
    strings = []
    for i in range(count):
        offset, = struct.unpack_from("<I", data, start + i * 4)
        while data[offset] & 128:
            offset += 1
        offset += 1
        strings.append(data[offset:data.index(b"\0", offset)].decode("utf-8", "replace"))
    count, start = struct.unpack_from("<II", data, 64)
    types = [strings[struct.unpack_from("<I", data, start + i * 4)[0]] for i in range(count)]
    count, start = struct.unpack_from("<II", data, 96)
    return [types[struct.unpack_from("<I", data, start + i * 32)[0]] for i in range(count)]


def signing_block(data):
    end=data.rfind(b"PK\x05\x06",max(0,len(data)-65557))
    if end<0: raise ValueError("APK end-of-central-directory not found")
    central,=struct.unpack_from("<I",data,end+16)
    if data[central-16:central]!=b"APK Sig Block 42": return b""
    size,=struct.unpack_from("<Q",data,central-24)
    start=central-size-8
    if start<0 or struct.unpack_from("<Q",data,start)[0]!=size: raise ValueError("Invalid OEM signing block")
    return data[start:central]


def retain_oem_certificate(original, target):
    """Keep the OEM signing identity for preinstalled-APK certificate collection.

    DEX changes invalidate content digests; this is not a signature verification
    bypass for user APK installation and must never be used for a data-app update.
    """
    block=signing_block(original.read_bytes())
    if not block: return
    data=target.read_bytes()
    end=data.rfind(b"PK\x05\x06",max(0,len(data)-65557))
    central,=struct.unpack_from("<I",data,end+16)
    updated=bytearray(data[:central]+block+data[central:])
    struct.pack_into("<I",updated,end+len(block)+16,central+len(block))
    target.write_bytes(updated)
    if signing_block(target.read_bytes())!=block: raise ValueError("OEM signing identity was not retained")


def parameter_words(descriptor):
    types = re.findall(r"\[*L[^;]+;|\[*[ZBCSIFJD]", descriptor.split(")")[0][1:])
    return sum(2 if t in ("J", "D") else 1 for t in types)


def wrap_method(text, descriptor, before="", after=""):
    """Retain the entire OEM implementation; a small typed wrapper delegates to it."""
    pattern = re.compile(r"^\.method ([^\n]*?) " + re.escape(descriptor) + r"\n.*?^\.end method", re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one concrete method: {descriptor} ({len(matches)})")
    match = matches[0]
    flags = match.group(1)
    if "native" in flags or "abstract" in flags or descriptor.startswith("<"):
        raise ValueError(f"Method cannot be wrapped: {descriptor}")
    owner = re.search(r"^\.class .* (L[^;]+;)$", text, re.M).group(1)
    name, signature = descriptor.split("(", 1)
    original = "acOriginal$" + descriptor
    renamed = match.group(0).replace(" " + descriptor + "\n", " " + original + "\n", 1)
    words = parameter_words("(" + signature) + (0 if "static" in flags.split() else 1)
    registers = "{}" if words == 0 else "{p0 .. p" + str(words - 1) + "}"
    kind = "static" if "static" in flags.split() else "direct" if "private" in flags.split() else "virtual"
    returns = signature.split(")")[1]
    suffix = "-object" if returns.startswith(("L", "[")) else "-wide" if returns in ("J", "D") else ""
    result = "" if returns == "V" else f"    move-result{suffix} v0\n"
    end = "    return-void" if returns == "V" else f"    return{suffix} v0"
    wrapper = (f".method {flags} {descriptor}\n    .locals 6\n\n{before}\n    :ac_delegate\n"
               f"    invoke-{kind}/range {registers}, {owner}->{original}\n{result}\n{after}\n{end}\n.end method")
    return text[:match.start()] + renamed + "\n\n" + wrapper + text[match.end():]


def run(command, log):
    result = subprocess.run([str(v) for v in command], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}; see external build log")


def build(args):
    adapter = runpy.run_path(str(args.adapter))["ADAPTER"] if args.adapter.suffix == ".py" else json.loads(args.adapter.read_text())
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Output must be a new directory under an existing parent")
    records = args.records.resolve()
    if records.is_relative_to(ROOT) or not records.parent.is_dir():
        raise ValueError("Records must be outside the source checkout")
    records.mkdir(exist_ok=True)
    inputs = {}
    for relative,expected in adapter.get("required_files",{}).items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts or digest(args.system/relative)!=expected:
            raise ValueError("Unknown adapter dependency: "+relative)
    for label, spec in adapter["targets"].items():
        path = args.system / spec["path"]
        if not path.is_file() or digest(path) != spec["sha256"]:
            raise ValueError(f"Unknown {label} input; provide a separately validated adapter")
        inputs[label] = path
    output.mkdir()
    cache=ROOT/"out/host-tools/artisan-control-cache"
    cache.mkdir(exist_ok=True)
    with (records / "build.log").open("w") as log, tempfile.TemporaryDirectory(prefix="artisan-control-") as temporary:
        temp = Path(temporary)
        classes = temp / "classes"
        dex = temp / "dex"
        classes.mkdir(); dex.mkdir()
        stubs=temp/"stubs";stubs.mkdir()
        run(["javac","--release","8","-classpath",args.android_jar,"-d",stubs,*sorted((SOURCE/"stubs").rglob("*.java"))],log)
        stub_jar=temp/"settings-stubs.jar"
        with zipfile.ZipFile(stub_jar,"w") as archive:
            for file in stubs.rglob("*.class"):archive.write(file,str(file.relative_to(stubs)))
        java = sorted((SOURCE / "src").rglob("*.java"))
        run(["javac", "--release", "8", "-classpath", str(args.android_jar)+os.pathsep+str(stubs), "-d", classes, *java], log)
        settings_classes = sorted((classes / "com/android/settings/artisan").rglob("*.class"))
        broker_classes=sorted((classes/"com/artisanrom/control").glob("RootBroker*.class"))
        hook_classes = sorted(p for p in classes.rglob("*.class") if p not in settings_classes and p not in broker_classes)
        # Reuse this DEX for the root broker so app-only releases do not require a framework rebuild.
        for label, selected in (("hooks", hook_classes), ("settings", settings_classes),("broker",broker_classes)):
            folder = dex / label; folder.mkdir()
            run(["java", "-cp", args.build_tools / "lib/d8.jar", "com.android.tools.r8.D8", "--min-api", "31",
                 "--lib", args.android_jar,"--classpath",stub_jar, "--output", folder, *selected], log)
        with zipfile.ZipFile(output/"ArtisanControlBroker.jar","w") as broker:
            broker.write(dex/"broker/classes.dex","classes.dex",compress_type=zipfile.ZIP_STORED)
        patched = []
        for label, path in inputs.items():
            rules = adapter["targets"][label].get("hooks", [])
            additions=adapter["targets"][label].get("add_methods", [])
            edits=adapter["targets"][label].get("edits", [])
            replacements = {}
            with zipfile.ZipFile(path) as z:
                for entry in z.namelist():
                    if not re.fullmatch(r"classes\d*\.dex", entry): continue
                    owners = set(dex_classes(z.read(entry)))
                    selected = [rule for rule in rules if rule["class"] in owners]
                    extra=[rule for rule in additions if rule["class"] in owners]
                    fragments=[rule for rule in edits if rule["class"] in owners]
                    transforms=adapter["targets"][label].get("transforms", [])
                    if not selected and not extra and not fragments and not transforms: continue
                    cache_key=hashlib.sha256(Path(__file__).read_bytes()+z.read(entry)+json.dumps([selected,extra,fragments,transforms],sort_keys=True).encode()).hexdigest()
                    cached=cache/(cache_key+".dex")
                    cached_hash=cache/(cache_key+".sha256")
                    if cached.is_file() and cached_hash.is_file() and digest(cached)==cached_hash.read_text().strip():
                        if set(dex_classes(cached.read_bytes()))!=owners:raise ValueError("Invalid cached class inventory")
                        replacements[entry]=cached
                        patched.extend({"target":label,"class":rule["class"],"method":rule["method"]} for rule in selected+extra+fragments)
                        continue
                    folder = temp / label / entry
                    run(["baksmali", "d", "--debug-info", "false", "-l", "-j", "8", "-o", folder, str(path) + "/" + entry], log)
                    for rule in selected:
                        smali = folder / (rule["class"][1:-1] + ".smali")
                        text = smali.read_text()
                        smali.write_text(wrap_method(text, rule["method"], rule.get("before", ""), rule.get("after", "")))
                        patched.append({"target":label,"class":rule["class"],"method":rule["method"]})
                    for rule in extra:
                        smali=folder/(rule["class"][1:-1]+".smali")
                        text=smali.read_text()
                        if re.search(r"^\.method .* "+re.escape(rule["method"])+r"$",text,re.M):
                            raise ValueError("Adapter addition would replace an OEM method")
                        smali.write_text(text+"\n"+rule["code"]+"\n")
                        patched.append({"target":label,"class":rule["class"],"method":rule["method"],"added_override":True})
                    for rule in fragments:
                        smali=folder/(rule["class"][1:-1]+".smali")
                        text=smali.read_text()
                        if text.count(rule["find"])!=1:raise ValueError("Pinned adapter fragment did not match once")
                        smali.write_text(text.replace(rule["find"],rule["replace"]))
                        patched.append({"target":label,"class":rule["class"],"method":rule["method"],"fragment":True})
                    for transform in transforms:
                        for smali in folder.rglob("*.smali"):
                            text=smali.read_text()
                            def changed(match):
                                register=match.group(1)
                                return match.group(0)+f"\n    invoke-static/range {{{register} .. {register}}}, {transform['helper']}\n    move-result {register}\n"
                            updated,n=re.subn(r"^    iget-boolean ([vp]\d+), [vp]\d+, "+re.escape(transform["field"])+r"$",changed,text,flags=re.M)
                            if n: smali.write_text(updated)
                    assembled = folder.with_suffix(".patched.dex")
                    run(["smali", "a", "-a", "35", "-j", "8", "-o", assembled, folder], log)
                    if assembled.read_bytes()[:4] != b"dex\n": raise ValueError("Assembler did not produce DEX")
                    # Method preservation: all original class definitions remain after assembly.
                    if set(dex_classes(assembled.read_bytes())) != owners: raise ValueError("Class inventory changed")
                    cached.write_bytes(assembled.read_bytes());cached_hash.write_text(digest(cached)+"\n")
                    replacements[entry] = cached
                if sum(1 for item in patched if item["target"]==label) != len(rules)+len(additions)+len(edits):
                    raise ValueError(f"An adapter owner was not found in {label}")
                target = output / (label + path.suffix)
                with zipfile.ZipFile(target, "w") as final:
                    for item in z.infolist():
                        data = replacements[item.filename].read_bytes() if item.filename in replacements else z.read(item.filename)
                        final.writestr(copy.copy(item), data)
                    if label in ("framework","settings"):
                        next_index = max(int(re.search(r"(\d*)\.dex$", n).group(1) or "1")
                                         for n in z.namelist() if re.fullmatch(r"classes\d*\.dex", n)) + 1
                        final.write(dex / ("hooks" if label=="framework" else "settings") / "classes.dex", f"classes{next_index}.dex", compress_type=zipfile.ZIP_STORED)
                    if label=="settings":
                        final.write(SOURCE/"features.json","assets/artisan/features.json")
                        final.writestr("assets/artisan/adapter.json",json.dumps({"id":adapter["id"],"features":adapter["features"]}))
                if path.suffix == ".apk":
                    # OEM certificate/resource entries are retained; no substitute OEM signing key is introduced.
                    next_file = output / (label + ".aligned.apk")
                    run([args.build_tools / "zipalign", "-f", "-p", "4", target, next_file], log)
                    next_file.replace(target)
                    retain_oem_certificate(path,target)
                    run([args.build_tools / "zipalign", "-c", "4", target], log)
                with zipfile.ZipFile(target) as result:
                    for name in z.namelist():
                        if name not in replacements and result.read(name) != z.read(name):
                            raise ValueError(f"Unrelated archive entry changed: {label}:{name}")
        manifest = {"schema":1,"adapter":adapter["id"],"package":"com.android.settings","surface":"native-settings-fragment",
                    "required_files":adapter.get("required_files",{}),
                    "features":adapter["features"],"patches":patched,
                    "inputs":{label:{"path":adapter["targets"][label]["path"],"sha256":digest(path)} for label,path in inputs.items()},
                    "outputs":{p.name:digest(p) for p in output.iterdir() if p.is_file()}}
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"adapter":manifest["adapter"],"patched_methods":len(patched),"outputs":manifest["outputs"]},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--system",type=Path,required=True)
    p.add_argument("--adapter",type=Path,required=True)
    p.add_argument("--build-tools",type=Path,required=True)
    p.add_argument("--android-jar",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--records",type=Path,required=True)
    build(p.parse_args())


if __name__=="__main__": main()
