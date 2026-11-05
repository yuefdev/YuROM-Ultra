#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only device/donor provenance check before any legacy work-tree mutation."""
import argparse
from pathlib import Path
import sys

DONOR_BUILD = "S948BXXU5BZJA"
STOCK_BUILD = "G975FXXSGHWC2"
DONOR = "SM-S948B_EUX"
STOCK = "SM-G975F_AUT"


def one_property(path, key):
    if not path.is_file():
        raise ValueError("Missing Android build properties: " + str(path))
    matches = []
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            if name.strip() == key:
                matches.append(value.strip())
    if len(matches) != 1:
        raise ValueError("Missing/duplicate property: " + key)
    return matches[0]


def verify(fw_dir: Path, kernel: Path) -> dict:
    donor, stock = fw_dir / DONOR, fw_dir / STOCK
    for directory in (donor, stock):
        if not (directory / ".extracted").is_file():
            raise ValueError("Prepared firmware is missing: " + str(directory))
    donor_props = donor / "system/system/build.prop"
    if (one_property(donor_props, "ro.build.version.incremental") != DONOR_BUILD or
            one_property(donor_props, "ro.build.version.sdk") != "37"):
        raise ValueError("Full public SM-S948B Android 17 firmware not present")
    system = donor / "system/system"
    if not (system / "framework/framework.jar").is_file():
        raise ValueError("Donor framework.jar is missing")
    if not (donor / "product").is_dir() or not (donor / "system_ext").is_dir():
        raise ValueError("Missing donor product/system_ext; never ship a debloated image")
    camera = system / "priv-app/SamsungCamera/SamsungCamera.apk"
    if not camera.is_file():
        raise ValueError("Modern donor SamsungCamera.apk is missing")
    vendor_props = stock / "vendor/build.prop"
    if (one_property(vendor_props, "ro.product.vendor.model") != "SM-G975F" or
            one_property(vendor_props, "ro.vendor.build.version.incremental") != STOCK_BUILD):
        raise ValueError("Only original SM-G975F vendor firmware is accepted")
    if not (stock / "vendor/etc/vintf/manifest.xml").is_file():
        raise ValueError("G975F VINTF/driver manifest is missing")
    for name in ("boot.img", "dtb.img", "dtbo.img"):
        if not (kernel / name).is_file():
            raise ValueError("Missing model-built G975F kernel image: " + name)
    # These facts are not sufficient to validate HALs, SELinux, init,
    # Camera, Play Services, SUSFS or a real S10+ boot.
    return {"donor": DONOR_BUILD, "stock": STOCK_BUILD, "model": "SM-G975F",
            "input_paths_present": True, "ready_for_flash": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware-dir", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.firmware_dir, args.kernel)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
