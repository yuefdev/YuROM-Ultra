#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wrap an exact full-image ZIP for recoveries whose ZIP front end lacks ZIP64."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from s10_models import MODELS, ROOT, digest, render_installer


def installer(payload_name, payload_sha256, binary_sha256):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.zip", payload_name)
            or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (payload_sha256, binary_sha256))):
        raise ValueError("Safe payload filename and exact SHA256 pins are required")
    return '''#!/sbin/sh
set -u
OUTFD="${2:-}"
SELF="${3:-}"
WORK=
case "$OUTFD" in ''|*[!0-9]*) echo 'Invalid recovery output descriptor' >&2; exit 1 ;; esac
# The recovery's mksh rejects high-numbered >& fds and does not reliably
# inherit shell-created fds. Keep TWRP's original fd and use procfs here.
ui() { printf 'ui_print %s\nui_print\n' "$*" >"/proc/self/fd/$OUTFD"; }
abort() { ui "ERROR: $*"; exit 1; }
cleanup() { [ -z "$WORK" ] || rm -rf "$WORK"; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
base="${SELF%/*}"
[ "$base" != "$SELF" ] || base=.
PAYLOAD="$base/@PAYLOAD@"
[ -f "$PAYLOAD" ] || abort 'Keep the matching full TWRP payload ZIP beside this installer ZIP.'
for tool in sha256sum unzip mktemp ln; do
    command -v "$tool" >/dev/null 2>&1 || abort "Recovery is missing $tool."
done
[ -x /sbin/busybox ] || abort 'The verified recovery BusyBox shell is required.'
ui 'YuROM Ultra ZIP64 compatibility launcher'
ui 'Verifying the complete matching payload ZIP before starting its original installer.'
actual="$(sha256sum "$PAYLOAD")" || abort 'Cannot hash the payload ZIP.'
[ "${actual%% *}" = '@PAYLOAD_SHA256@' ] || abort 'The payload ZIP is corrupt or belongs to another build/model.'
WORK="$(mktemp -d /tmp/artisan-bootstrap.XXXXXX)" || abort 'Cannot create launcher directory.'
unzip -p "$PAYLOAD" META-INF/com/google/android/update-binary > "$WORK/update-binary" || abort 'Cannot read the original installer.'
actual="$(sha256sum "$WORK/update-binary")" || abort 'Cannot hash the original installer.'
[ "${actual%% *}" = '@BINARY_SHA256@' ] || abort 'The original installer does not match this launcher.'
# Older S10 recoveries expose only the original UFS platform alias. Create
# the standard tmpfs alias when absent; the original validates every target.
if [ ! -e /dev/block/by-name ] && [ ! -L /dev/block/by-name ]; then
    for part in vbmeta system vendor dtb dtbo boot; do
        [ -b "/dev/block/platform/13d60000.ufs/by-name/$part" ] || abort 'Missing original S10 UFS partition.'
    done
    ln -s /dev/block/platform/13d60000.ufs/by-name /dev/block/by-name || abort 'Cannot create the temporary UFS alias.'
fi
# All model/layout/clean-data/chunk/readback checks remain in the exact original.
/sbin/busybox sh "$WORK/update-binary" "${1:-3}" "$OUTFD" "$PAYLOAD"
exit "$?"
'''.replace("@PAYLOAD@", payload_name).replace("@PAYLOAD_SHA256@", payload_sha256).replace("@BINARY_SHA256@", binary_sha256)


def build(payload, output, records):
    if (output.exists() or not output.parent.is_dir() or not payload.is_file()
            or output.resolve() == payload.resolve() or not records.is_dir() or records.resolve().is_relative_to(ROOT)):
        raise ValueError("Existing payload, fresh output and external records are required")
    with zipfile.ZipFile(payload) as source:
        manifest = json.loads(source.read("artisan/manifest.json"))
        model = manifest.get("model")
        binary = source.read("META-INF/com/google/android/update-binary")
        if (model not in MODELS or binary != render_installer(model).encode()
                or not manifest.get("clean_install_required") or manifest.get("automatic_data_format") is not False
                or manifest.get("repartition") is not False):
            raise ValueError("The registered original-layout clean-install payload is required")
    payload_sha256 = digest(payload)
    binary_sha256 = hashlib.sha256(binary).hexdigest()
    script = installer(payload.name, payload_sha256, binary_sha256)
    metadata = {"schema": 1, "kind": "twrp-zip64-compatibility-launcher", "model": model, "version": manifest["version"],
                "payload_file": payload.name, "payload_bytes": payload.stat().st_size, "payload_sha256": payload_sha256,
                "original_installer_sha256": binary_sha256, "original_installer_checks_preserved": True,
                "launcher_file": output.name, "launch_via_sideload_supported": False,
                "recovery_shell": "busybox-sh", "original_recovery_output_descriptor_retained": True,
                "legacy_ufs_alias_supported": True}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=False) as archive:
        info = zipfile.ZipInfo("META-INF/com/google/android/update-binary", (2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100755 << 16
        archive.writestr(info, script.encode())
        archive.writestr("META-INF/com/google/android/updater-script", "# ZIP64 compatibility launcher; use its exact sibling payload.\n")
        archive.writestr("artisan/bootstrap.json", json.dumps(metadata, indent=2) + "\n")
        archive.writestr("INSTALL.md", "# TWRP ZIP64 compatibility launcher\n\n"
                         "Keep this installer ZIP and `" + payload.name + "` together in the same directory.\n"
                         "After the documented backup and Format Data steps, install this small ZIP in TWRP.\n"
                         "It verifies the entire payload and runs its unmodified model-checked installer.\n"
                         "ADB sideload does not provide access to sibling files; use a normal mounted directory.\n")
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(checksum + "  " + output.name + "\n")
    metadata.update({"launcher_bytes": output.stat().st_size, "launcher_sha256": checksum})
    with (records / "bootstrap-package.json").open("x") as stream:
        json.dump(metadata, stream, indent=2)
        stream.write("\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("payload", "output", "records"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.payload, args.output, args.records)
