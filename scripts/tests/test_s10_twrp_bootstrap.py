#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove the ZIP64 launcher rejects absent/corrupt siblings before original execution."""
import hashlib
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_s10_twrp_bootstrap import installer


def main():
    with tempfile.TemporaryDirectory(prefix="s10-twrp-bootstrap-") as temporary:
        root = Path(temporary)
        payload = root / "ArtisanROM_payload.zip"
        original = b"#!/bin/sh\nprintf 'ui_print Original installer reached\\nui_print\\n' >&\"$2\"\nprintf original > \"$3.started\"\nexit 7\n"
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("META-INF/com/google/android/update-binary", original)
        packed = payload.read_bytes()
        script = installer(payload.name, hashlib.sha256(packed).hexdigest(), hashlib.sha256(original).hexdigest())
        # Host fixture only: preserve the actual command/arguments, use the host shell.
        path = root / "update-binary"
        alias = root / "by-name"
        alias.symlink_to(root, target_is_directory=True)
        path.write_text(script.replace('/sbin/busybox sh "$WORK/update-binary"', '/bin/bash "$WORK/update-binary"')
                       .replace('[ -x /sbin/busybox ]', '[ -x /bin/bash ]').replace('/dev/block/by-name', str(alias)))
        command = ["sh", str(path), "3", "1", str(root / "launcher.zip")]
        started = Path(str(payload) + ".started")
        payload.unlink()
        result = subprocess.run(command, capture_output=True)
        assert result.returncode and not started.exists() and b"Keep the matching" in result.stdout
        payload.write_bytes(packed + b"corrupt")
        result = subprocess.run(command, capture_output=True)
        assert result.returncode and not started.exists() and b"corrupt or belongs" in result.stdout
        payload.write_bytes(packed)
        result = subprocess.run(command, capture_output=True)
        assert result.returncode == 7 and started.read_text() == "original"
        assert b"Original installer reached" in result.stdout
        # Match the real TWRP failure: its pipe can be fd 30, which legacy
        # mksh cannot use in dynamic >& redirections. The launcher forwards
        # that original fd to the explicitly selected compatible shell.
        with (root / "recovery-output").open("wb") as output:
            high_fd = fcntl.fcntl(output.fileno(), fcntl.F_DUPFD, 30)
            try:
                high_command = ["sh", str(path), "3", str(high_fd), str(root / "launcher.zip")]
                result = subprocess.run(high_command, pass_fds=(high_fd,), capture_output=True)
                assert result.returncode == 7 and b"illegal file descriptor" not in result.stderr
            finally:
                os.close(high_fd)
        assert b"Original installer reached" in (root / "recovery-output").read_bytes()
        for name in ("../other.zip", "a';echo.zip", "a b.zip", "/tmp/a.zip"):
            try:
                installer(name, "0" * 64, "1" * 64)
            except ValueError:
                pass
            else:
                raise AssertionError("Unsafe payload filename accepted")
    print("PASS: absent/corrupt payload refuses before original execution; exact original and exit status preserved; high-numbered recovery output works; unsafe names rejected")


if __name__ == "__main__":
    main()
