#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the experimental G973F images from root TWRP without repartitioning."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_verified_images(installation, stage, shell, record):
    for item in installation:
        name = item["partition"]
        device = item.get("device", "/dev/block/by-name/" + name)
        print("Writing and verifying", name, flush=True)
        output = shell("dd if=" + stage + "/" + name + ".img of=" + device + " bs=4194304 conv=fsync 2>&1", timeout=600)
        readback = shell("head -c " + str(item["size"]) + " " + device + " | sha256sum", timeout=300).split()[0]
        if readback != item["sha256"]:
            raise RuntimeError("Flashed image readback checksum mismatch: " + name)
        record({"partition": name, "size": item["size"], "sha256": readback, "readback_verified": True}, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--format-data", action="store_true", help="Irreversibly erase all internal user data after verified image writes")
    parser.add_argument("--resume-uploaded", action="store_true", help="Resume verified uploads only when a prior pre-write attempt halted")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    previous = None
    if args.resume_uploaded and (args.records / "state.json").is_file():
        previous = json.loads((args.records / "state.json").read_text())
    if (not args.adb.is_file() or (args.records.exists() and not args.resume_uploaded)
            or not args.records.parent.is_dir() or args.records.resolve().is_relative_to(checkout)):
        parser.error("Verified ADB, a fresh external records destination and an existing parent are required")
    if args.resume_uploaded and (not previous or previous.get("status") != "failed" or previous.get("writes") or previous.get("data_formatted")):
        parser.error("Only a halted attempt with no partition writes or data format can resume its uploads")
    layout = json.loads((checkout / "target/beyond1lte/oneui9/stock-layout.json").read_text())
    candidate = json.loads((args.candidate / "input.json").read_text())
    images = json.loads((args.candidate / "images.json").read_text())
    kernel = json.loads((args.kernel / "input.json").read_text())
    backup = json.loads((args.backup / "state.json").read_text())
    evidence = json.loads((args.evidence / "result.json").read_text())
    if (candidate.get("model") != "SM-G973F" or candidate.get("donor_build") != "S942BXXU4ZZH6"
            or candidate.get("stock_build") != "G973FXXSGHWC1" or candidate.get("repartition") is not False
            or set(candidate.get("legacy_vintf_inputs", {})) != {"etc/vintf/compatibility_matrix.device.xml", "etc/vintf/manifest/legacy-vndk31.xml"}):
        parser.error("The verified original-layout candidate with legacy framework VINTF inputs is required")
    if (kernel.get("source_commit") != "a97afb2c431802523a89fb875a3faadb7dcaac26"
            or kernel.get("netlink_xperm_capability_index") != 9 or not kernel.get("perf_events_restrict")
            or kernel.get("stock_fstab_sha256") != candidate["kernel"]["stock_fstab_sha256"]):
        parser.error("The compatible indexed netlink-xperm/perf-restriction kernel is required")
    if backup.get("status") != "completed" or not backup.get("bootstrap_readback_verified") or len(backup.get("partitions", {})) != 16:
        parser.error("Completed independently verified device rollback backups are required")
    if evidence.get("vendor_count") != 90 or evidence.get("vendor_failures") or not evidence.get("scope", "").startswith("actual donor generated namespaces"):
        parser.error("Actual generated-namespace vendor dependency checks are required")
    vintf = (args.evidence / "vintf-selinux-visible.log").read_text()
    if "VintfObject::checkCompatibility?                         GOOD" not in vintf:
        parser.error("The actual donor VINTF compatibility result must pass")
    installation = []
    for name in ("system", "vendor", "dtb", "dtbo", "boot"):
        source = args.candidate if name in ("system", "vendor") else args.kernel
        metadata = images["images"][name + ".img"] if name in ("system", "vendor") else kernel["images"][name + ".img"]
        path = source / (name + ".img")
        if path.stat().st_size != metadata["size"] or metadata["size"] > layout["partitions"][name]["bytes"] or digest(path) != metadata["sha256"]:
            parser.error(f"Installation image size/checksum mismatch: {name}")
        rollback = backup["partitions"][name]
        backup_image = args.backup / rollback.get("file", name + ".img")
        if (rollback["size"] != layout["partitions"][name]["bytes"] or not rollback.get("device_sha256_verified")
                or backup_image.stat().st_size != rollback["size"] or digest(backup_image) != rollback["sha256"]):
            parser.error(f"Verified device rollback backup changed: {name}")
        installation.append({"partition": name, "source": path, "size": metadata["size"], "sha256": metadata["sha256"]})
    args.records.mkdir(exist_ok=args.resume_uploaded)
    state = {"status": "preflight", "model": "SM-G973F", "repartition": False, "writes": [],
             "data_format_requested": args.format_data, "data_formatted": False, "full_boot_tested": False,
             "runtime_hal_registration_tested": False,
             "install_set": [{key: str(value) if isinstance(value, Path) else value for key, value in item.items()} for item in installation]}
    if previous:
        if previous.get("install_set") != state["install_set"] or previous.get("data_format_requested") != args.format_data:
            parser.error("Resumed installation inputs or the requested data format changed")
        with (args.records / "state.before-resume.json").open("x") as stream:
            json.dump(previous, stream, indent=2)

    def save():
        (args.records / "state.json").write_text(json.dumps(state, indent=2) + "\n")

    def shell(command, timeout=30):
        result = subprocess.run([str(args.adb), "-s", args.serial, "shell", command], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", timeout=timeout)
        if result.returncode:
            raise RuntimeError(command + "\n" + result.stdout + result.stderr)
        return result.stdout.strip()

    stage = "/data/oneui9-stock-layout-install"
    save()
    try:
        identity = shell("id; getprop ro.twrp.version; getprop ro.product.device")
        if "uid=0(root)" not in identity or "3.7.0_9-1" not in identity or "beyond1lte" not in identity:
            raise RuntimeError("Expected official beyond1lte TWRP root")
        if int(shell("cat /sys/class/power_supply/battery/capacity")) < 30:
            raise RuntimeError("Charge the device before installation")
        free_kib = int(shell("df -k /data").splitlines()[-1].split()[-3])
        if free_kib * 1024 < sum(item["size"] for item in installation) + 1024 ** 3:
            raise RuntimeError("Insufficient device space for the verified installation payloads")
        if args.resume_uploaded:
            shell("test -d " + stage)
        else:
            shell("test -d /data && test ! -e " + stage + " && mkdir " + stage)
        for name, actual in backup["partitions"].items():
            if shell("readlink -f /dev/block/by-name/" + name) != actual["target"] or int(shell("blockdev --getsize64 /dev/block/by-name/" + name)) != actual["size"]:
                raise RuntimeError("Connected device no longer matches the verified backup partition layout: " + name)
        if shell("sha256sum /dev/block/by-name/vbmeta").split()[0] != backup["partitions"]["vbmeta"]["sha256"]:
            raise RuntimeError("Disabled-AVB readback changed")
        state["status"] = "uploading"
        save()
        for item in installation:
            name = item["partition"]
            destination = stage + "/" + name + ".img"
            if not args.resume_uploaded:
                print("Uploading verified image", name, flush=True)
                with (args.records / (name + ".push.log")).open("xb") as log:
                    subprocess.run([str(args.adb), "-s", args.serial, "push", str(item["source"]), destination],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            if shell("sha256sum " + destination, timeout=300).split()[0] != item["sha256"]:
                raise RuntimeError("Uploaded image checksum mismatch: " + name)
        preview = "/data/s10-port-runtime-preview-gnu-v3/root"
        mountpoints = [line.split()[1] for line in shell("cat /proc/mounts").splitlines() if line.split()[1] == preview or line.split()[1].startswith(preview + "/")]
        for path in sorted(mountpoints, key=lambda value: value.count("/"), reverse=True):
            shell("umount " + path)
        for item in installation:
            device = "/dev/block/by-name/" + item["partition"]
            target = shell("readlink -f " + device)
            for line in reversed(shell("cat /proc/mounts").splitlines()):
                source = line.split()[0]
                if source in (device, target) or source.endswith("/by-name/" + item["partition"]):
                    shell("umount " + line.split()[1])
        mounts = shell("cat /proc/mounts")
        for item in installation:
            device = "/dev/block/by-name/" + item["partition"]
            target = shell("readlink -f " + device)
            if any(line.split()[0] in (device, target) or line.split()[0].endswith("/by-name/" + item["partition"]) for line in mounts.splitlines()):
                raise RuntimeError("Target partition must be unmounted before writing: " + item["partition"])
        state["status"] = "writing"
        save()
        def record(entry, output):
            (args.records / (entry["partition"] + ".write.log")).write_text(output + "\n")
            state["writes"].append(entry)
            save()
        write_verified_images(installation, stage, shell, record)
        if args.format_data:
            for line in shell("losetup -a").splitlines():
                if "/data/s10-port-runtime-preview-gnu-v3/" in line:
                    loop = line.split(":", 1)[0]
                    if any(entry.split()[0] == loop for entry in shell("cat /proc/mounts").splitlines()):
                        raise RuntimeError("Runtime preview loop is still mounted before data format")
                    shell("losetup -d " + loop)
            state["status"] = "formatting-data"
            save()
            print("Formatting internal user data with explicit --format-data request.", flush=True)
            output = shell("twrp format data", timeout=180)
            (args.records / "format-data.log").write_text(output + "\n")
            shell("twrp mount /data", timeout=30)
            data_mounts = [line.split() for line in shell("cat /proc/mounts").splitlines() if line.split()[1] == "/data"]
            if (len(data_mounts) != 1 or not data_mounts[0][0].endswith("/by-name/userdata") or data_mounts[0][2] != "ext4"
                    or shell("test ! -e " + stage + " && test -d /data && df -k /data") == ""):
                raise RuntimeError("Data format completion could not be verified")
            state["data_formatted"] = True
        state["status"] = "installed-awaiting-first-boot"
        save()
        print(json.dumps(state, indent=2))
    except Exception as error:
        state.update(status="failed", error=str(error))
        save()
        raise


if __name__ == "__main__":
    main()
