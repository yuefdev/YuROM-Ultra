#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage the public telemetry endpoint; client participation remains disabled until explicitly enabled."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


def configure(system, version, endpoint=None):
    if endpoint is None:
        profile = json.loads((Path(__file__).resolve().parents[1] / "target/beyond1lte/oneui9/telemetry.json").read_text())
        if profile.get("schema") != 1:
            raise ValueError("Unsupported telemetry endpoint profile")
        endpoint = profile["endpoint"]
    if not re.fullmatch(r"v[0-9]{1,4}(?:[._-][A-Za-z0-9]+){0,4}", version):
        raise ValueError("Invalid telemetry ROM version")
    if endpoint:
        url = urlsplit(endpoint)
        if (url.scheme != "https" or not url.hostname or not re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", url.hostname)
                or url.port is not None or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("Use the public HTTPS Worker origin without a path, credentials or query")
        endpoint = "https://" + url.hostname
    target = system / "etc/artisan-telemetry.json"
    if target.exists():
        raise ValueError("A telemetry endpoint is already staged")
    target.write_text(json.dumps({"schema": 1, "endpoint": endpoint, "build": version}, indent=2) + "\n")
    os.chown(target, 0, 0)
    os.chmod(target, 0o644)
    os.setxattr(target, "security.selinux", os.getxattr(system / "etc/floating_feature.xml", "security.selinux"))
    return {"configured": bool(endpoint), "opt_in_required": True, "files": ["etc/artisan-telemetry.json"],
            "endpoint": endpoint,
            "transport": "https", "hardware_identifiers_collected": False, "raw_logs_uploaded": False}
