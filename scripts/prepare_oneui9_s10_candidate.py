#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare an experimental merged system and HWC1 vendor policy for S10."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def properties(path):
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), []).append(value.strip())
    return values


def set_property(path, key, value, expected=None):
    current = properties(path).get(key, [])
    if len(current) > 1 or (expected is not None and current != [expected]):
        raise RuntimeError(f"Unexpected donor property: {key}")
    lines = path.read_text().splitlines()
    if current:
        lines = [f"{key}={value}" if not line.lstrip().startswith("#") and line.split("=", 1)[0].strip() == key else line for line in lines]
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


def reconcile_vendor_service_property(system, vendor):
    """Retain HWC1's security label for its own Widevine provisioning service."""
    name = "init.svc.vendor.wvkprov_server_hal"
    platform = system / "system_ext/etc/selinux/system_ext_property_contexts"
    original = vendor / "etc/selinux/vendor_property_contexts"
    matches = []
    for path, context in ((platform, "u:object_r:wvkprov_prop:s0"),
                          (original, "u:object_r:vendor_wvkprov_prop:s0")):
        entries = [line for line in path.read_text().splitlines() if line.split("#", 1)[0].split()[:1] == [name]]
        if len(entries) != 1 or entries[0].split() != [name, context]:
            raise RuntimeError("Unexpected Widevine service property ownership or match semantics")
        matches.append(entries[0])
    # Write in place to preserve ownership, mode and SELinux xattrs.
    platform.write_text("\n".join(line for line in platform.read_text().splitlines() if line != matches[0]) + "\n")
    return {"property": name, "retained_context": "u:object_r:vendor_wvkprov_prop:s0",
            "removed_donor_duplicate": True, "vendor_contexts_unchanged": True,
              "policy_allow_rules_changed": False}


def reconcile_s10_display_features(system):
    """Select the maintained S10 brightness/AOD contract, retaining other features."""
    path = system / "etc/floating_feature.xml"
    text = path.read_text()
    root = ET.fromstring(text)
    changes = {}
    for name, before, after in (
            ("SEC_FLOATING_FEATURE_LCD_CONFIG_CONTROL_AUTO_BRIGHTNESS", "5", "4"),
            ("SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_BRIGHTNESS_ANIMATION", "1", "0"),
            ("SEC_FLOATING_FEATURE_LCD_CONFIG_AOD_FULLSCREEN", "1", "0")):
        old, new = f"<{name}>{before}</{name}>", f"<{name}>{after}</{name}>"
        nodes = root.findall(name)
        if len(nodes) != 1 or nodes[0].text != before or text.count(old) != 1:
            raise RuntimeError(f"Unexpected donor display feature: {name}")
        text = text.replace(old, new, 1)
        changes[name] = {"from": before, "to": after}
    # All inputs are checked before this in-place write; labels and mode survive.
    path.write_text(text)
    return {"features": changes, "automatic_brightness_retained": True,
            "extra_brightness_unchanged": True, "device_wake_tested": False}


def retain_adbd_domain(system):
    """Keep authenticated root adbd in its USB-capable domain, not debug-only su."""
    path = system / "etc/init/hw/init.usb.rc"
    text = path.read_text()
    before = "service adbd /system/bin/adbd --root_seclabel=u:r:su:s0\n"
    if (text.count(before) != 1 or text.count("service adbd ") != 1
            or "    seclabel u:r:adbd:s0\n" not in text or text.count("    updatable\n") != 1):
        raise RuntimeError("Unexpected donor adbd service or SELinux domain")
    # APEX init must not override this domain with its debug-only su argument.
    # The executable still comes from the unchanged, signed adbd APEX.
    path.write_text(text.replace(before, "service adbd /apex/com.android.adbd/bin/adbd\n", 1).replace("    updatable\n", "", 1))
    return {"daemon_domain": "adbd", "removed_root_domain_override": "su",
            "apex_service_override_allowed": False, "apex_executable_unchanged": True,
            "adb_authentication_unchanged": True, "policy_allow_rules_added": False}


def init_enforcing_patch(data):
    """Restore enforcement in the pinned init's real SELinux setup decision."""
    expected = "1f061d2da71aaaabcd8a86614a17e0b262012924aac9fca9e5dbf06018749b9b"
    before = bytes.fromhex("9d3106941f04007100010054000080529f310694a0000034")
    if hashlib.sha256(data).hexdigest() != expected or data.count(before) != 1:
        raise RuntimeError("Unexpected donor init; refusing SELinux enforcing patch")
    offset = data.index(before) + 12
    patched = data[:offset] + bytes.fromhex("20008052") + data[offset + 4:]
    return patched, {"original_sha256": expected, "sha256": hashlib.sha256(patched).hexdigest(),
                     "file_offset": offset, "instruction_bytes": 4,
                     "change": "security_setenforce argument 0 to 1; already-enforcing path retained",
                     "policy_allow_rules_added": False}


def import_legacy_ueventd_rules(system, vendor):
    """Let ueventd own the HWC1 device permissions before TEEGRIS starts."""
    path = system / "etc/ueventd.rc"
    text = path.read_text()
    marker = "import /vendor/etc/ueventd.rc\n"
    legacy = vendor / "ueventd.rc"
    if (text.count(marker) != 1 or "import /vendor/ueventd.rc" in text
            or not legacy.is_file() or (vendor / "etc/ueventd.rc").exists()):
        raise RuntimeError("Unexpected ueventd import or legacy vendor rules")
    rules = [line.split() for line in legacy.read_text().splitlines() if not line.lstrip().startswith("#")]
    if [rule for rule in rules if rule[:1] == ["/dev/tzdev"]] != [["/dev/tzdev", "0666", "system", "system"]]:
        raise RuntimeError("Unexpected HWC1 TEEGRIS device permissions")
    path.write_text(text.replace(marker, marker + "import /vendor/ueventd.rc\n", 1))
    return {"import": "/vendor/ueventd.rc", "vendor_rules_sha256": digest(legacy),
            "device_permission_owner": "ueventd", "stock_rule_bytes_unchanged": True,
            "policy_allow_rules_added": False}


def legacy_mapper_patch(data, architecture):
    """Enable mapper 3/2 fallback, including the donor's inlined and preload paths."""
    patches = {
        "arm64": ("466dffbd2087a5a0c18b84717437e7204128af9343a9ec42657ba9839a309d0f",
                  (("constructor", "1f8c0071ac03005400028052", "1f8c00711f2003d500028052"),
                   ("inlined_graphic_buffer", "1f8c0071ac05005400028052", "1f8c00711f2003d500028052"),
                   ("preload", "1f8c00716c000054f0a1ff97", "1f8c00711f2003d5f0a1ff97")), 4, 4),
        "arm64-swcodec": ("1ba2b7348b2235e0cbd604fc6dc4ad587682150585ffe1601b426c9538c94b71",
                          (("constructor", "1f8c0071ac03005400028052", "1f8c00711f2003d500028052"),
                           ("inlined_graphic_buffer", "1f8c0071ac05005400028052", "1f8c00711f2003d500028052"),
                           ("preload", "1f8c00716c000054149cff97", "1f8c00711f2003d5149cff97")), 4, 4),
        "arm": ("f00f065cc36f1b5f0f9b44ae635aa7b9f6a8c0797135856c58b7634c22c26ed3",
                (("constructor", "23281bdc0820", "232800bf0820"),
                 ("preload", "232803dc06f020ef", "232800bf06f020ef")), 2, 2),
    }
    checksum, sites, offset, size = patches[architecture]
    sites = [(name, bytes.fromhex(before), bytes.fromhex(after)) for name, before, after in sites]
    if hashlib.sha256(data).hexdigest() != checksum or any(data.count(before) != 1 for _, before, _ in sites):
        raise RuntimeError(f"Unexpected {architecture} donor libui; refusing legacy mapper patch")
    patched, instructions = data, []
    for name, before, after in sites:
        position = data.index(before)
        patched = patched[:position] + after + patched[position + len(before):]
        instructions.append({"site": name, "file_offset": position + offset, "bytes": size})
    return patched, {"original_sha256": checksum, "sha256": hashlib.sha256(patched).hexdigest(),
                     "instructions": instructions,
                     "change": "SDK > 35 rejection branch to NOP; mapper 5/4 preference retained"}


def configure_legacy_graphics_and_usb(system, vendor):
    """Use S10's existing graphics HAL and let HWC1 init own its USB gadget."""
    manifest = ET.parse(vendor / "etc/vintf/manifest.xml").getroot()
    mappers = [hal for hal in manifest.findall("hal") if hal.findtext("name") == "android.hardware.graphics.mapper"]
    if (len(mappers) != 1 or mappers[0].findtext("version") != "2.0"
            or mappers[0].findtext("transport") != "passthrough"
            or properties(vendor / "build.prop").get("ro.product.first_api_level") != ["28"]):
        raise RuntimeError("Expected S10 legacy passthrough graphics mapper and first API 28")
    usb = system / "etc/init/xgsi-usb.rc"
    if (digest(usb) != "13a9ee6d95e36579f0a7cc6b0923353103002eda68d7bbd643506bec8d413804"
            or digest(vendor / "etc/init/init.exynos9820.usb.rc") != "1b33275541f99092539cdaf9c8e36ece7cc139e39c54c52d228e8679d6359723"
            or digest(system / "bin/surfaceflinger") != "bb981c3593f0f17f16c44077bfdbd21c408d50fc98b7a913d579dd04ca6cccd2"
            or properties(system / "build.prop").get("debug.renderengine.backend")):
        raise RuntimeError("Unexpected donor renderer configuration or S10 USB init inputs")
    planned, changes = [], {}
    for directory, architecture in (("lib64", "arm64"), ("lib", "arm")):
        relative = directory + "/libui.so"
        path = system / relative
        patched, record = legacy_mapper_patch(path.read_bytes(), architecture)
        planned.append((path, patched))
        changes[relative] = record
    # All inputs are checked before writing; in-place writes retain Android metadata.
    for path, patched in planned:
        path.write_bytes(patched)
    set_property(system / "build.prop", "debug.renderengine.backend", "skiaglthreaded")
    usb.write_text("# HWC1 vendor init owns the S10 USB gadget and functionfs mounts.\n"
                   "on init\n    setprop sys.usb.controller 10c00000.dwc3\n")
    return {"system_mapper_clients": changes, "renderengine_backend": "skiaglthreaded",
            "usb_gadget_owner": "unchanged HWC1 vendor init", "usb_controller": "10c00000.dwc3",
            "reported_sdk_changed": False, "vendor_graphics_changed": False,
            "apex_payloads_changed": False, "secure_adb_changed": False,
            "device_boot_tested": False}


def configure_swcodec_and_hwui(system):
    """Apply the pinned media mapper fallback before any updatable service starts."""
    archive = system / "apex/com.android.media.swcodec.capex"
    expected = "290bb69544f669150c7c4f883904cf06a166291db92d24e823bef70823892951"
    rc = system / "etc/init/hw/init.rc"
    directory = system / "lib64/s10-swcodec"
    target = directory / "libui.so"
    marker = "    wait_for_prop keystore.module_hash.sent true\n    perform_apex_config\n"
    text = rc.read_text()
    if (digest(archive) != expected or directory.exists() or text.count(marker) != 1
            or "/system/lib64/s10-swcodec/" in text
            or properties(system / "build.prop").get("debug.hwui.renderer")):
        raise RuntimeError("Unexpected donor swcodec, APEX activation or HWUI configuration")
    with tempfile.TemporaryDirectory(prefix="s10-swcodec-") as temporary:
        root = Path(temporary)
        original = root / "original.apex"
        payload = root / "apex_payload.img"
        with zipfile.ZipFile(archive) as packed, packed.open("original_apex") as source, original.open("xb") as output:
            shutil.copyfileobj(source, output, 4 * 1024 * 1024)
        with zipfile.ZipFile(original) as packed, packed.open("apex_payload.img") as source, payload.open("xb") as output:
            shutil.copyfileobj(source, output, 4 * 1024 * 1024)
        # debugfs is read-only. The library hash also rejects a missing entry or bad output.
        result = subprocess.run(["debugfs", "-R", "cat /lib64/libui.so", str(payload)],
                                check=True, capture_output=True)
        patched, metadata = legacy_mapper_patch(result.stdout, "arm64-swcodec")
    # Keep both APEX signatures intact; only this module's pinned libui is overlaid.
    # Revalidate this integration whenever changing the donor swcodec APEX.
    directory.mkdir(mode=0o755)
    os.chown(directory, 0, 0)
    os.setxattr(directory, "security.selinux", b"u:object_r:system_lib_file:s0")
    target.write_bytes(patched)
    os.chmod(target, 0o644)
    os.chown(target, 0, 0)
    os.setxattr(target, "security.selinux", b"u:object_r:system_lib_file:s0")
    binding = ("    # The signed swcodec APEX has its own SDK-gated mapper client.\n"
               "    mount none /system/lib64/s10-swcodec/libui.so "
               "/apex/com.android.media.swcodec/lib64/libui.so bind\n")
    rc.write_text(text.replace(marker, marker + binding, 1))
    set_property(system / "build.prop", "debug.hwui.renderer", "skiagl")
    files = {str(path.relative_to(system)): digest(path) for path in (target, rc, system / "build.prop")}
    return {"archive_sha256": expected, "mapper_patch": metadata, "files": files,
            "mount_order": "after activated APEX configuration, before zygote and core services",
            "hwui_renderer": "skiagl", "apex_archive_unchanged": True,
            "global_system_libui_unchanged": True, "policy_unchanged": True,
            "device_cold_boot_tested": False}


def prepare_cache_metadata(system):
    """Provide persistent metadata on the existing cache, with matching path labels."""
    rc = system / "etc/init/aconfigd.rc"
    contexts = system / "etc/selinux/plat_file_contexts"
    if (digest(rc) != "78d6bb311aa7126384da4b59780d4a87d9b321c4fd211d04e1339fbd8975447b"
            or digest(contexts) != "5a8648bf340c742a8507a1937e02ec1e6a22baa0bc457ef39a1db90c7ad52902"):
        raise RuntimeError("Unexpected donor metadata initialization or file contexts")
    original = contexts.read_text()
    aliases = [line.replace("/metadata", "/cache/oneui9-metadata", 1)
               for line in original.splitlines() if line.startswith("/metadata")]
    if not aliases or not any("aconfig_storage_metadata_file" in line for line in aliases):
        raise RuntimeError("Expected all donor metadata labels, including aconfig storage")
    initialization = ("on early-init\n"
                      "    # Cache is mounted in first stage on the stock-layout S10.\n"
                      "    mkdir /cache/oneui9-metadata 0755 root system\n"
                      "    mount none /cache/oneui9-metadata /metadata bind\n"
                      "    restorecon_recursive /metadata\n")
    text = rc.read_text()
    if text.count("on early-init\n") != 1:
        raise RuntimeError("Expected one early metadata initialization action")
    rc.write_text(text.replace("on early-init\n", initialization))
    # The framework also relabels /cache later; both paths must resolve identically.
    contexts.write_text(original + "\n# Stock-layout S10 metadata backing aliases.\n" + "\n".join(aliases) + "\n")
    return {"backing_directory": "/cache/oneui9-metadata", "mountpoint": "/metadata",
            "persistent": True, "requires_first_stage_cache": True, "file_context_aliases": len(aliases),
            "feature_flags_changed": False, "services_disabled": False, "repartition": False,
            "device_boot_tested": False}


def reconcile_first_stage_cache(vendor):
    """Prevent HWC1 mount_all from remounting the already mounted stock cache."""
    path = vendor / "etc/fstab.exynos9820"
    if digest(path) != "4c5ca4d70ebbe8919dab429973d54f8783a8030e84ecf15894ce0d647caee234":
        raise RuntimeError("Unexpected HWC1 vendor fstab")
    original = path.read_text()
    lines = original.splitlines(keepends=True)
    found = [index for index, line in enumerate(lines) if line.split()[:2] == ["/dev/block/by-name/cache", "/cache"]]
    if len(found) != 1 or lines[found[0]].split()[4] != "wait,check":
        raise RuntimeError("Expected exactly one original cache mount")
    lines[found[0]] = lines[found[0]].replace("wait,check", "wait,check,first_stage_mount")
    path.write_text("".join(lines))
    return {"cache_first_stage_mount": True, "prevent_duplicate_cache_mount": True,
            "all_other_fstab_lines_unchanged": True, "data_contract_changed": False}


def reconcile_data_encryption(vendor):
    """Keep FBE enabled using the same public crypto modes as the kernel ramdisk."""
    from build_oneui9_s10_kernel import USERDATA_ENCRYPTION, compatible_fbe_fstab

    path = vendor / "etc/fstab.exynos9820"
    path.write_text(compatible_fbe_fstab(path.read_text()))
    return {"from": "ice", "to": USERDATA_ENCRYPTION, "file_encryption_enabled": True,
            "data_filesystem": "ext4", "requires_clean_data": True,
            "rollback": "restore matching verified boot/vendor images; userdata is not reverse-migrated"}


def migrate_audio(checkout, system, vendor):
    """Reuse the maintained Exynos 9820 HIDL 6 wrappers and matched service."""
    if not (system / "lib64/libaudiohal@6.0.so").is_file():
        raise RuntimeError("The donor does not support the selected HIDL 6 audio client")
    source = checkout / "platform/exynos9820/patches/audio/vendor"
    copies = {}
    for file in sorted(source.rglob("*.so")):
        relative = file.relative_to(source)
        destination = vendor / relative
        template = vendor / relative.parts[0] / "hw/android.hardware.audio@5.0-impl.so"
        if not template.is_file() or not destination.parent.is_dir():
            raise RuntimeError(f"Missing original audio metadata template: {relative}")
        label = os.getxattr(template, "security.selinux")
        destination.write_bytes(file.read_bytes())
        os.chmod(destination, 0o644)
        os.chown(destination, 0, 0)
        os.setxattr(destination, "security.selinux", label)
        copies[str(relative)] = digest(destination)
    relative = Path("bin/hw/android.hardware.audio.service")
    destination = vendor / relative
    service = checkout / "platform/exynos9820/patches/vendor/vendor" / relative
    metadata = destination.stat()
    attributes = {name: os.getxattr(destination, name) for name in os.listxattr(destination)}
    destination.write_bytes(service.read_bytes())
    os.chmod(destination, metadata.st_mode & 0o7777)
    os.chown(destination, metadata.st_uid, metadata.st_gid)
    for name, value in attributes.items():
        os.setxattr(destination, name, value)
    copies[str(relative)] = digest(destination)
    rc = (vendor / "etc/init/android.hardware.audio.service.rc").read_text()
    if "service vendor.audio-hal /vendor/bin/hw/android.hardware.audio.service" not in rc:
        raise RuntimeError("Unexpected original audio service entry point")
    path = vendor / "etc/vintf/manifest.xml"
    tree = ET.parse(path)
    changed = []
    for hal in tree.getroot().findall("hal"):
        name = hal.findtext("name")
        if name not in ("android.hardware.audio", "android.hardware.audio.effect"):
            continue
        versions = hal.findall("version")
        if len(versions) != 1 or versions[0].text != "5.0":
            raise RuntimeError(f"Unexpected original audio interface version: {name}")
        versions[0].text = "6.0"
        for fqname in hal.findall("fqname"):
            if not fqname.text.startswith("@5.0::"):
                raise RuntimeError(f"Unexpected original audio service declaration: {name}")
            fqname.text = "@6.0::" + fqname.text.removeprefix("@5.0::")
        changed.append(name)
    if len(changed) != 2:
        raise RuntimeError("Expected both original audio and effect HAL declarations")
    # Writing in place preserves the original manifest's metadata.
    tree.write(path, encoding="unicode")
    return {"from": "5.0", "to": "6.0", "copied_inputs": copies,
            "legacy_libraries_retained": True, "runtime_tested": False,
            "rollback": "restore the verified original HWC1 vendor image"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--stock-vintf", type=Path, required=True)
    parser.add_argument("--kernel-manifest", type=Path, required=True)
    parser.add_argument("--secilc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--artisan-control", type=Path, help="Verified portable Artisan Control bundle")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    if os.geteuid() != 0 or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Linux root, an existing candidate parent and a new destination are required")
    if not args.records.is_dir() or args.records.resolve().is_relative_to(checkout):
        parser.error("An existing external validation records directory is required")
    donor = json.loads((args.donor / "input.json").read_text())
    stock = json.loads((args.stock / "input.json").read_text())
    stock_vintf = json.loads((args.stock_vintf / "input.json").read_text())
    kernel = json.loads(args.kernel_manifest.read_text())
    if donor.get("kind") != "verified-oneui9-donor" or donor.get("build") != "S942BXXU4ZZH6" or stock.get("build") != "G973FXXSGHWC1" or stock.get("model") != "SM-G973F":
        parser.error("The exact verified donor and original HWC1 inputs are required")
    if kernel.get("kind") != "experimental-oneui9-s10-netlink-xperm-kernel" or kernel.get("netlink_xperm_capability_index") != 9:
        parser.error("The built indexed netlink-xperm kernel is required")
    if not kernel.get("cache_metadata_backend"):
        parser.error("The stock-layout first-stage cache metadata ramdisk is required")
    if kernel.get("userdata_encryption") != "aes-256-xts:aes-256-cts:v2" or not kernel.get("requires_clean_data"):
        parser.error("Matching supported FBE modes and an explicitly clean-data kernel contract are required")
    if (stock_vintf.get("model") != stock.get("model") or stock_vintf.get("build") != stock.get("build")
            or stock_vintf.get("stock_system_sha256") != stock["images"]["system.img"]["sha256"]):
        parser.error("Legacy VINTF inputs must come from the same verified HWC1 system")
    for name, manifest, root in (("donor", donor, args.donor), ("stock", stock, args.stock)):
        if digest(root / "images/system.img") != manifest["images"]["system.img"]["sha256"]:
            parser.error(f"The {name} system input changed after verification")
    print("Verified donor and HWC1 image checksums.", flush=True)
    args.output.mkdir()
    tree = args.output / "tree"
    vendor = args.output / "vendor"
    print("Copying the donor tree with Android metadata.", flush=True)
    subprocess.run(["cp", "-a", "--reflink=auto", str(args.donor / "tree"), str(tree)], check=True)
    print("Copying the original vendor tree with Android metadata.", flush=True)
    subprocess.run(["cp", "-a", "--reflink=auto", str(args.stock / "vendor"), str(vendor)], check=True)
    print("Applying scoped S10 and audio compatibility changes.", flush=True)
    system = tree / "system"
    for partition, file in (("system", system / "build.prop"),
                            ("system_ext", system / "system_ext/etc/build.prop"),
                            ("product", system / "product/etc/build.prop")):
        set_property(file, f"ro.product.{partition}.model", "SM-G973F", "SM-S942B")
        set_property(file, f"ro.product.{partition}.device", "beyond1", "essi")
        set_property(file, f"ro.product.{partition}.name", "beyond1ltexx", "m1sxxx")
        for suffix, value in (("abilist", "arm64-v8a,armeabi-v7a,armeabi"),
                              ("abilist32", "armeabi-v7a,armeabi"), ("abilist64", "arm64-v8a")):
            set_property(file, f"ro.product.{partition}.cpu.{suffix}", value)
    for key, value in (("hwservicemanager.always_sets_disabled", "false"), ("ro.secure", "1"),
                       ("ro.adb.secure", "1"), ("ro.zygote", "zygote64_32"),
                       ("persist.bluetooth.a2dp_offload.disabled", "true")):
        set_property(system / "build.prop", key, value)
    for name, target in (("product", "/system/product"), ("system_ext", "/system/system_ext")):
        link = tree / name
        if not link.is_symlink() or os.readlink(link) != target:
            raise RuntimeError(f"Unexpected merged-system root link: {name}")
    copied = {}
    selected = args.stock / "system-files/system"
    for source in sorted(selected.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(selected)
        destination = system / relative
        if relative.parts[:2] == ("etc", "vintf"):
            matrix = ET.parse(source).getroot()
            if matrix.get("type") != "framework" or matrix.get("level") not in ("3", "4", "5", "6") or destination.exists():
                raise RuntimeError(f"Unexpected original FCM input: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-a", str(source), str(destination)], check=True)
        copied[str(relative)] = digest(destination)
    for file in ("bin/init", "bin/app_process32", "bin/app_process64", "system_ext/bin/hwservicemanager", "apex/com.android.vndk.v31.apex"):
        if not (system / file).is_file():
            raise RuntimeError(f"Missing required legacy compatibility component: {file}")
    legacy_vintf = {}
    for source_name, destination_name in (
            ("system/compatibility_matrix.device.xml", "etc/vintf/compatibility_matrix.device.xml"),
            ("system_ext/manifest.xml", "etc/vintf/manifest/legacy-vndk31.xml")):
        source = args.stock_vintf / source_name
        destination = system / destination_name
        checksum = digest(source)
        if checksum != stock_vintf["files"][source_name] or destination.exists() or not destination.parent.is_dir():
            raise RuntimeError(f"Unexpected legacy VINTF input or destination: {source_name}")
        xml = ET.parse(source).getroot()
        if source_name.startswith("system_ext/"):
            if xml.tag != "manifest" or xml.get("type") != "framework" or xml.findtext("vendor-ndk/version") != "31":
                raise RuntimeError("Original VNDK 31 framework declaration is required")
        elif (xml.tag != "compatibility-matrix" or xml.get("type") != "framework" or xml.get("level") is not None
              or "31.0" not in [item.text for item in xml.findall("sepolicy/sepolicy-version")]):
            raise RuntimeError("Original level-independent HWC1 SELinux compatibility matrix is required")
        subprocess.run(["cp", "-a", str(source), str(destination)], check=True)
        legacy_vintf[destination_name] = checksum
    audio = migrate_audio(checkout, system, vendor)
    from utils.s10_hdmi_audio import configure as configure_hdmi_audio
    hdmi_audio = configure_hdmi_audio(system, vendor)
    service_property = reconcile_vendor_service_property(system, vendor)
    graphics_usb = configure_legacy_graphics_and_usb(system, vendor)
    from s10_schedtune import configure_legacy_schedtune
    scheduler_compatibility = configure_legacy_schedtune(system, vendor)
    from s10_native_zygote import configure_native_zygote
    native_zygote_compatibility = configure_native_zygote(system, vendor)
    from s10_boot_performance import configure_boot_performance
    boot_performance = configure_boot_performance(vendor)
    media_compatibility = configure_swcodec_and_hwui(system)
    display_features = reconcile_s10_display_features(system)
    from s10_settings_branding import configure_settings_branding
    settings_branding = configure_settings_branding(checkout, system)
    artisan_control = None
    ce_storage_compatibility = None
    if args.artisan_control:
        from artisan_control import configure_artisan_control
        artisan_control = configure_artisan_control(system, vendor, args.artisan_control)
        settings_branding["settings_original_sha256"] = settings_branding["settings_sha256"]
        settings_branding["settings_sha256"] = hashlib.sha256((system / "priv-app/SecSettings/SecSettings.apk").read_bytes()).hexdigest()
        settings_branding["settings_apk_unmodified"] = False
        settings_branding["settings_resources_unmodified"] = True
    else:
        from s10_ce_storage import configure_tokenless_ce
        ce_storage_compatibility = configure_tokenless_ce(system)
    adbd_domain = retain_adbd_domain(system)
    patched_init, init_enforcement = init_enforcing_patch((system / "bin/init").read_bytes())
    (system / "bin/init").write_bytes(patched_init)
    ueventd_import = import_legacy_ueventd_rules(system, vendor)
    metadata_backend = prepare_cache_metadata(system)
    cache_mount = reconcile_first_stage_cache(vendor)
    data_encryption = reconcile_data_encryption(vendor)
    policy = vendor / "etc/selinux"
    version = (policy / "plat_sepolicy_vers.txt").read_text().strip()
    if version != "31.0":
        raise RuntimeError("Unexpected original vendor policy version")
    inputs = [system / "etc/selinux/plat_sepolicy.cil", system / "etc/selinux/mapping/31.0.cil"]
    compat = system / "etc/selinux/mapping/31.0.compat.cil"
    if compat.exists():
        inputs.append(compat)
    for partition in ("system_ext", "product"):
        base = system / partition / "etc/selinux"
        inputs.append(base / (partition + "_sepolicy.cil"))
        for suffix in (".cil", ".compat.cil"):
            path = base / "mapping" / (version + suffix)
            if path.exists():
                inputs.append(path)
    inputs += [policy / "plat_pub_versioned.cil", policy / "vendor_sepolicy.cil"]
    if any("(permissive " in path.read_text() for path in inputs):
        raise RuntimeError("The combined policy contains permissive domains")
    command = [str(args.secilc), "-m", "-M", "true", "-G", "-c", "31", "-f", "/dev/null"]
    print("Compiling strict and Android-init policy variants.", flush=True)
    with (args.records / "candidate-policy-strict.log").open("xb") as stream:
        strict = subprocess.run(command + ["-o", str(args.records / "candidate-policy-strict.bin")] + list(map(str, inputs)),
                                stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    # Stock Android init uses -N for mixed-version split policy compilation.
    # This does not disable enforcement or add any allow/permissive statements.
    with (args.records / "candidate-policy-init.log").open("xb") as stream:
        subprocess.run(command + ["-N", "-o", str(policy / "precompiled_sepolicy")] + list(map(str, inputs)),
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    for partition, base in (("plat", system / "etc/selinux"),
                            ("system_ext", system / "system_ext/etc/selinux"),
                            ("product", system / "product/etc/selinux")):
        name = partition + "_sepolicy_and_mapping.sha256"
        destination = policy / ("precompiled_sepolicy." + name)
        subprocess.run(["cp", "-a", str(base / name), str(destination)], check=True)
        os.setxattr(destination, "security.selinux", os.getxattr(policy / "vendor_sepolicy.cil", "security.selinux"))
    os.chmod(policy / "precompiled_sepolicy", 0o644)
    os.setxattr(policy / "precompiled_sepolicy", "security.selinux", os.getxattr(policy / "vendor_sepolicy.cil", "security.selinux"))
    result = {"schema": 1, "kind": "experimental-oneui9-s10-merged-system-with-hwc1-vendor",
              "model": "SM-G973F", "donor_build": donor["build"], "stock_build": stock["build"],
               "copied_stock_inputs": copied, "kernel": kernel,
               "legacy_vintf_inputs": legacy_vintf,
                "vendor_service_property_reconciliation": service_property,
                   "legacy_graphics_and_usb_compatibility": graphics_usb,
                   "s10_legacy_scheduler_compatibility": scheduler_compatibility,
                   "s10_native_zygote_compatibility": native_zygote_compatibility,
                   "s10_boot_performance": boot_performance,
                   "s10_media_compatibility": media_compatibility,
                   "s10_ce_storage_compatibility": ce_storage_compatibility,
                 "s10_display_features": display_features,
                   "s10_settings_branding": settings_branding,
                   "artisan_control": artisan_control,
                 "adbd_domain_reconciliation": adbd_domain,
                 "init_enforcement_restoration": init_enforcement,
                 "legacy_ueventd_import": ueventd_import,
                "cache_metadata_backend": metadata_backend,
                 "vendor_cache_mount_reconciliation": cache_mount,
                 "userdata_encryption_migration": data_encryption,
               "audio_interface_migration": audio,
               "s10_hdmi_audio_compatibility": hdmi_audio,
              "binary_policy_version": 31, "binary_policy_sha256": digest(policy / "precompiled_sepolicy"),
              "strict_neverallow_check_exit_code": strict.returncode,
              "policy_compile_mode": "upstream Android init -m -M true -G -N",
              "permissive_domains": False, "device_boot_tested": False, "native_hal_compatibility": "pending",
              "ready_for_installation": False, "repartition": False}
    with (args.output / "input.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Prepared experimental system and HWC1 vendor candidate; policy compiled for kernel version 31.")
    print("Actual linker/HAL compatibility and device boot are still pending.")


if __name__ == "__main__":
    main()
