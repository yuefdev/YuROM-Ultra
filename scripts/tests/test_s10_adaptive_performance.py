#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the production Java tuning policy against isolated host fixtures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="s10-adaptive-performance-") as directory:
        source = ROOT / "packages/ArtisanControl/src/com/artisanrom/control/RootBrokerPerformancePolicy.java"
        probe = ROOT / "scripts/tests/android/artisan-settings/PerformancePolicyProbe.java"
        learner = source.with_name("RootBrokerPerformanceLearner.java")
        subprocess.run(["javac", "--release", "8", "-d", directory, str(source), str(learner), str(probe)], check=True)
        subprocess.run(["java", "-cp", directory, "com.artisanrom.control.PerformancePolicyProbe"], check=True)
