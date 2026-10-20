#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the production telemetry redactor against private-content fixtures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="artisan-telemetry-") as directory:
        source = ROOT / "packages/ArtisanControl/src/com/artisanrom/control/RootBrokerCrashSummary.java"
        probe = ROOT / "scripts/tests/android/artisan-settings/TelemetryPrivacyProbe.java"
        subprocess.run(["javac", "--release", "8", "-d", directory, str(source), str(probe)], check=True)
        subprocess.run(["java", "-cp", directory, "com.artisanrom.control.TelemetryPrivacyProbe"], check=True)
