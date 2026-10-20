#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the experimental netlink-xperm kernel for the stock S10 layout."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

PIN = "a97afb2c431802523a89fb875a3faadb7dcaac26"
CLANG_HASH = "85a113b981c1e4c81fb98afce61b2eb74c425dc51c3116fee08d3a863e611a22"
CLANG_GIT_TREE = "a86cb6592a29d53254d3a88ff2d8282233a273e2"
USERDATA_ENCRYPTION = "aes-256-xts:aes-256-cts:v2"
BOOT_CMDLINE = "loop.max_part=7 enforcing=1"
MODELS = {"SM-G973F": "beyond1lte", "SM-G970F": "beyond0lte", "SM-G975F": "beyond2lte"}
PERFORMANCE_PATCH = "6d353b6bc4d6af95d4ef9215f2b80825593dddfb2ac66efffdd38bca6ab654e5"


def toolchain_tree(path):
    """Check an extracted compiler against the pinned Git tree, including modes."""
    entries = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.encode() + (b"/" if p.is_dir() and not p.is_symlink() else b"")):
        if entry.is_symlink():
            data, mode = os.readlink(entry).encode(), b"120000"
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).digest()
        elif entry.is_dir():
            entries.append(b"40000 " + entry.name.encode() + b"\0" + bytes.fromhex(toolchain_tree(entry)))
            continue
        else:
            mode = b"100755" if entry.stat().st_mode & 0o111 else b"100644"
            checksum = hashlib.sha1(b"blob " + str(entry.stat().st_size).encode() + b"\0")
            with entry.open("rb") as stream:
                while block := stream.read(4 * 1024 * 1024):
                    checksum.update(block)
            blob = checksum.digest()
        entries.append(mode + b" " + entry.name.encode() + b"\0" + blob)
    data = b"".join(entries)
    return hashlib.sha1(b"tree " + str(len(data)).encode() + b"\0" + data).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cache_first_stage_fstab(stock_fstab):
    """Make the existing stock cache available before second-stage early-init."""
    lines = stock_fstab.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines)
               if not line.lstrip().startswith("#") and len(line.split()) >= 2 and line.split()[1] == "/cache"]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one stock cache mount")
    index = matches[0]
    fields = lines[index].split()
    if (len(fields) != 5 or fields[:3] != ["/dev/block/by-name/cache", "/cache", "ext4"]
            or fields[4] != "wait,check"):
        raise RuntimeError("Unexpected stock cache mount contract")
    lines[index] = lines[index].replace("wait,check", "wait,check,first_stage_mount")
    return "".join(lines)


def compatible_fbe_fstab(stock_fstab):
    """Use supported fscrypt modes instead of Samsung's private ICE mode 127."""
    lines = stock_fstab.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines)
               if not line.lstrip().startswith("#") and line.split()[1:2] == ["/data"]]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one stock userdata mount")
    index = matches[0]
    fields = lines[index].split()
    if (len(fields) != 5 or fields[:3] != ["/dev/block/by-name/userdata", "/data", "ext4"]
            or [flag for flag in fields[4].split(",") if flag.startswith("fileencryption=")] != ["fileencryption=ice"]
            or "quota" not in fields[4].split(",")):
        raise RuntimeError("Expected the original ext4/ICE userdata contract before FBE migration")
    lines[index] = lines[index].replace("fileencryption=ice", "fileencryption=" + USERDATA_ENCRYPTION)
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    compiler = parser.add_mutually_exclusive_group(required=True)
    compiler.add_argument("--clang-archive", type=Path)
    compiler.add_argument("--clang", type=Path, help="Extracted compiler; the complete pinned Git tree is verified")
    parser.add_argument("--model", choices=MODELS, default="SM-G973F")
    parser.add_argument("--stock", type=Path, help="Verified model stock inputs, required for family builds")
    parser.add_argument("--source-manifest", type=Path, help="Reviewed performance patch and additional source hashes")
    parser.add_argument("--stock-fstab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    if os.geteuid() != 0 or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Linux root, an existing kernel output parent and a new destination are required")
    source_commit = subprocess.check_output(["git", "-C", str(args.kernel), "rev-parse", "HEAD"], text=True).strip()
    if source_commit != PIN or (args.clang_archive and digest(args.clang_archive) != CLANG_HASH):
        parser.error("The pinned kernel source and verified Android Clang archive are required")
    source_diff = subprocess.check_output(["git", "-C", str(args.kernel), "diff", "--binary", "HEAD", "--"])
    untracked = subprocess.check_output(["git", "-C", str(args.kernel), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
    performance = None
    if args.source_manifest:
        performance = json.loads(args.source_manifest.read_text())
        if (performance.get("source_commit") != PIN or performance.get("source_patch_sha256") != PERFORMANCE_PATCH
                or hashlib.sha256(source_diff).hexdigest() != PERFORMANCE_PATCH):
            parser.error("The reviewed performance source patch changed")
        required = {"drivers/soc/samsung/cal-if/exynos9820-oc.h", "drivers/soc/samsung/exynos-hiu-budget.h"}
        if not required.issubset(untracked) or set(untracked) - set(performance["new_sources"]):
            parser.error("Unreviewed or missing additional kernel source files")
        if any(digest(args.kernel / name) != performance["new_sources"][name] for name in untracked):
            parser.error("An additional kernel source changed after review")
    elif untracked:
        parser.error("Untracked kernel source files must be reviewed before building")
    stock = json.loads((args.stock / "input.json").read_text()) if args.stock else None
    if args.model != "SM-G973F" and (not stock or stock.get("model") != args.model
            or stock.get("kind") != "verified-s10-family-hwc2-stock-inputs"):
        parser.error("Matching verified stock inputs are required for the selected model")
    if stock and digest(args.stock_fstab) != digest(args.stock / "vendor/etc/fstab.exynos9820"):
        parser.error("The model's own stock fstab is required")
    header = (args.kernel / "security/selinux/include/security.h").read_text()
    if "POLICYDB_CAPABILITY_NETLINK_XPERM = 9" not in header:
        parser.error("The indexed netlink-xperm backport is required")
    stock_fstab = args.stock_fstab.read_text()
    data = [line.split() for line in stock_fstab.splitlines() if not line.startswith("#") and len(line.split()) >= 5 and line.split()[1] == "/data"]
    if len(data) != 1 or data[0][2] != "ext4" or "fileencryption=ice" not in data[0][4]:
        parser.error("The actual stock ext4/ICE userdata fstab is required")
    toolchain = args.clang.resolve() if args.clang else args.output / "clang"
    if args.clang:
        if toolchain_tree(toolchain) != CLANG_GIT_TREE:
            parser.error("The extracted compiler does not match the pinned Git tree")
        args.output.mkdir()
    else:
        args.output.mkdir()
        toolchain.mkdir()
        with tarfile.open(args.clang_archive) as archive:
            archive.extractall(toolchain, filter="data")
    subprocess.run([str(toolchain / "bin/clang"), "--version"], check=True)
    obj = args.output / "obj"
    environment = dict(os.environ, PATH=str(toolchain / "bin") + ":" + os.environ["PATH"])
    make = ["make", "-C", str(args.kernel), f"O={obj}", "ARCH=arm64", "LLVM=1", "LLVM_IAS=1",
            "CROSS_COMPILE=aarch64-linux-gnu-", "CROSS_COMPILE_ARM32=arm-linux-gnueabi-", f"-j{args.jobs}"]
    subprocess.run(make + ["exynos9820_defconfig", MODELS[args.model] + ".config"], env=environment, check=True)
    # HWC1's light HAL already writes native hundredth-brightness units.
    # The newer-HWC multiplier would scale those a second time after resume.
    subprocess.run(["bash", str(args.kernel / "scripts/config"), "--file", str(obj / ".config"),
                    "--disable", "ONEUI7_WORKAROUND", "--enable", "SECURITY_PERF_EVENTS_RESTRICT"], check=True)
    if performance:
        subprocess.run(["bash", str(args.kernel / "scripts/config"), "--file", str(obj / ".config"),
                        "--set-str", "CMDLINE", "exynos9820_cpu_oc=3016000 exynos9820_cluster_oc=1 exynos9820_gpu_oc=806000",
                        "--enable", "CMDLINE_EXTEND", "--disable", "CMDLINE_FROM_BOOTLOADER", "--disable", "CMDLINE_FORCE"], check=True)
    subprocess.run(make + ["olddefconfig"], env=environment, check=True)
    config = (obj / ".config").read_text()
    if "# CONFIG_ONEUI7_WORKAROUND is not set" not in config.splitlines():
        raise RuntimeError("The original HWC1 brightness units must not be multiplied again")
    for required in ("CONFIG_EROFS_FS=y", "CONFIG_EROFS_FS_ZIP=y", "CONFIG_EROFS_FS_SECURITY=y", "CONFIG_SECURITY_SELINUX=y",
                     "CONFIG_SECURITY_PERF_EVENTS_RESTRICT=y", "CONFIG_FS_ENCRYPTION=y", "CONFIG_CRYPTO_AES=y",
                     "CONFIG_CRYPTO_XTS=y", "CONFIG_CRYPTO_CTS=y"):
        if required not in config.splitlines():
            raise RuntimeError(f"Missing mandatory kernel feature: {required}")
    hardware = {"SM-G970F": ("CONFIG_CAMERA_BSS_V00=y", "CONFIG_EXYNOS_DECON_LCD_S6E3FA7=y",
                             "CONFIG_SENSORS_ET5XX=y", "# CONFIG_SENSORS_QBT2000 is not set"),
                "SM-G975F": ("CONFIG_CAMERA_BSS_V02=y", "CONFIG_CAMERA_CIS_4HA_OBJ=y",
                             "CONFIG_SENSORS_QBT2000=y")}
    for required in hardware.get(args.model, ()):
        if required not in config.splitlines():
            raise RuntimeError(f"Missing model-specific kernel feature: {required}")
    subprocess.run(make + ["Image", "dtbs"], env=environment, check=True)
    ramdisk = args.output / "ramdisk"
    subprocess.run(["cp", "-a", str(args.kernel / "build/ramdisk"), str(ramdisk)], check=True)
    first_stage = ["# Experimental stock-layout OS mounts.",
                   "/dev/block/by-name/system /system erofs ro wait,first_stage_mount",
                   "/dev/block/by-name/system /system ext4 ro wait,first_stage_mount",
                   "/dev/block/by-name/vendor /vendor erofs ro wait,first_stage_mount",
                   "/dev/block/by-name/vendor /vendor ext4 ro wait,first_stage_mount"]
    (ramdisk / "fstab.exynos9820").write_text("\n".join(first_stage) + "\n" + compatible_fbe_fstab(cache_first_stage_fstab(stock_fstab)))
    other = ramdisk / "fstab.exynos9825"
    if other.exists():
        other.unlink()
    names = ["."] + sorted("./" + str(path.relative_to(ramdisk)) for path in ramdisk.rglob("*"))
    cpio = subprocess.run(["cpio", "-o", "-H", "newc", "-R", "root:root"], cwd=ramdisk,
                          input=("\n".join(names) + "\n").encode(), stdout=subprocess.PIPE, check=True)
    packed = args.output / "ramdisk.cpio.gz"
    packed.write_bytes(gzip.compress(cpio.stdout, mtime=0))
    tools = args.kernel / "toolchain"
    for image, config_name, directory in (("dtb.img", "exynos9820.cfg", "exynos"),
                                           ("dtbo.img", MODELS[args.model] + ".cfg", "samsung")):
        subprocess.run([str(tools / "mkdtimg"), "cfg_create", str(args.output / image),
                        str(args.kernel / "build/dtconfigs" / config_name), "-d",
                        str(obj / "arch/arm64/boot/dts" / directory)], check=True)
    board = "SRPRI28B016KU"
    if stock:
        boot = args.stock / "images/boot.img"
        if digest(boot) != stock["images"]["boot.img"]["sha256"]:
            raise RuntimeError("The model stock boot image changed")
        with boot.open("rb") as stream:
            header = stream.read(64)
        if header[:8] != b"ANDROID!":
            raise RuntimeError("Expected an original Android boot header")
        board = header[48:64].split(b"\0")[0].decode("ascii")
    subprocess.run([str(tools / "mkbootimg"), "--base", "0x10000000", "--board", board,
                    "--cmdline", BOOT_CMDLINE, "--hashtype", "sha1", "--header_version", "1",
                    "--kernel", str(obj / "arch/arm64/boot/Image"), "--kernel_offset", "0x00008000",
                    "--os_patch_level", "2026-08", "--os_version", "17.0.0", "--pagesize", "2048",
                    "--ramdisk", str(packed), "--ramdisk_offset", "0xF0000000", "--second_offset", "0xF0000000",
                    "--tags_offset", "0x00000100", "-o", str(args.output / "boot.img")], check=True)
    layout = json.loads((Path(__file__).resolve().parent.parent / "target/beyond1lte/oneui9/stock-layout.json").read_text())
    if stock:
        layout = {"partitions": stock["partitions"]}
        # The boot-time performance guard hashes the complete block device.
        # Supply every byte, including a zero-filled tail, rather than inheriting
        # a previous ROM's boot footer or padding.
        with (args.output / "boot.img").open("ab") as stream:
            if stream.tell() > layout["partitions"]["boot"]["bytes"]:
                raise RuntimeError("Boot image exceeds the model's original partition")
            stream.truncate(layout["partitions"]["boot"]["bytes"])
    images = {}
    for name in ("boot", "dtb", "dtbo"):
        path = args.output / (name + ".img")
        if path.stat().st_size > layout["partitions"][name]["bytes"]:
            raise RuntimeError(f"Kernel image exceeds the actual stock partition: {name}")
        images[path.name] = {"size": path.stat().st_size, "sha256": digest(path)}
    result = {"schema": 1, "kind": "experimental-oneui9-s10-netlink-xperm-kernel",
              "model": args.model, "device": MODELS[args.model],
              "source_commit": source_commit, "source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
              "toolchain_archive_sha256": CLANG_HASH, "kernel_config_sha256": digest(obj / ".config"),
              "toolchain_git_tree": CLANG_GIT_TREE,
               "stock_fstab_sha256": digest(args.stock_fstab), "netlink_xperm_capability_index": 9,
                 "perf_events_restrict": True,
                  "selinux_boot_enforcing": True, "legacy_brightness_multiplier": False,
                 "cache_metadata_backend": True,
                 "userdata_encryption": USERDATA_ENCRYPTION, "requires_clean_data": True,
               "images": images, "device_boot_tested": False, "ready_for_installation": False}
    if performance:
        result["performance_source_patch_sha256"] = PERFORMANCE_PATCH
        result["performance_profile"] = {key: performance[key] for key in
                                         ("cpu_oc_target_khz", "gpu_oc_target_khz", "cluster_oc_requested")}
    with (args.output / "input.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Built the experimental stock-layout S10 kernel; device boot and policy load still require verification.")


if __name__ == "__main__":
    main()
