# YuROM Ultra V35 R32 · Installation guide

[← Project home](README.md) · [R32 downloads](https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-r32) · [Detailed release notes](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/RELEASE_NOTES.md)

## Supported devices and firmware

| Device | Model | Codename | Required firmware base |
| --- | --- | --- | --- |
| Galaxy S10e | SM-G970F | `beyond0lte` | `G970FXXSGHWC2` |
| Galaxy S10 | SM-G973F | `beyond1lte` | `G973FXXSGHWC1` |
| Galaxy S10+ | SM-G975F | `beyond2lte` | `G975FXXSGHWC2` |

Exynos only, with an unlocked bootloader and compatible model-specific TWRP.
No Snapdragon, Korean N or S10 5G support. The ROM does not update firmware,
recovery, EFS, modem, bootloader or the partition table.

## Downloads

There is **one full ROM per model**, plus its small matching installer. There
is no separate large UPDATE ROM.

### GitHub: reconstruct the transport pieces

From [the R32 release](https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-r32),
download these files for your actual model:

- All three `*_TWRP.zip.001`, `.002` and `.003` transport pieces.
- Its matching `*_INSTALLER_r1.zip`.
- `DOWNLOADS.json` and `join_yurom.py`.
- `SHA256SUMS.txt` and your model's `VALIDATION.json`.

Use **Python 3.11+** on NTFS or a Linux filesystem supporting hardlinks:

```sh
python join_yurom.py SM-G973F
```

Substitute `SM-G970F` for S10e or `SM-G975F` for S10+. Leave room for both the
pieces and the reconstructed roughly 4.5 GiB ZIP. The helper verifies every
piece, the complete payload and its matching installer. Keep the two final
ZIPs together without renaming them.

**Do not flash numbered pieces. Do not mix Beta/r4 helpers, manifests or
installers with R32.**

### Google Drive

The **[R32 Drive mirror](https://drive.google.com/drive/folders/1vLh8Ph07n7LyGFLhw2T9XUOmm2U5KwxZ)**
contains complete ZIPs. Download the full ROM, its matching small
`INSTALLER_r1.zip`, SHA256 sidecars and `VALIDATION.json` from your exact folder:

| Device | Full ZIP folder |
| --- | --- |
| S10e / SM-G970F | [Open Drive folder](https://drive.google.com/drive/folders/1KH4D3dJlZ_tJdBGWeHY_PHKLN2cVFdbJ) |
| S10 / SM-G973F | [Open Drive folder](https://drive.google.com/drive/folders/1dOxXv9clPfY6UCODNax_VxuzCGkLh_Ta) |
| S10+ / SM-G975F | [Open Drive folder](https://drive.google.com/drive/folders/1tatTfaFrxppRarjdhJpSWefQDHs90kwt) |

**No part joining or Python is needed for Drive downloads.** If Drive wraps
multiple selected files in an outer download ZIP, extract that outer ZIP
and keep the two original ROM/installer ZIPs separate, together and unrenamed.

Previous Beta/r2/r7 files have been moved into the Drive archive without
permanent deletion. Existing TWRP folders and public model-folder links are
preserved. The [v35-beta GitHub release](https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-beta)
is also historical, not another R32 download.

## Back up outside the phone

Save personal files and a complete matching rollback set externally before
flashing. A flash is not transactional: an interrupted write can leave a
mixed system. On a write/readback error, do not boot or blindly retry; restore
the complete matching backup.

Any separately chosen **manual Format Data irreversibly erases apps, accounts,
photos and internal storage**, including ROM files saved there. Do not format
merely to bypass an installer rejection.

## Choose the supported path

| Current state | Supported handling |
| --- | --- |
| Exact original model-specific `v35-beta` | Data-preserving upgrade. **Do not wipe or format.** All six source images must match their pins. |
| Already fresh ext4 userdata | Install the same full ROM and small installer; no automatic format. |
| Another ROM, encryption scheme, changed source boot/root or later build | Not a supported no-wipe upgrade. Stop on rejection; a separate clean migration needs explicit consent and external backups. |

The source gate checks **System, Vendor, Boot, DTB, DTBO and vbmeta before
writing**. Modified system/vendor, rooted or otherwise changed original-beta
boot, partial previous flashes and the current development r32 are not
approved upgrade sources.

## Flash the matching small installer

1. Keep the complete ROM ZIP and matching `INSTALLER_r1.zip` in one directory
   on readable storage. Use exFAT microSD/OTG or readable internal storage;
   FAT32 cannot hold the full ROM.
2. In compatible TWRP, keep readable **ext4 `/data` mounted**. Unmount
   System/System Root and Vendor. For a verified upgrade, leave user data intact.
3. Flash the **small installer**, not the large ZIP64 ROM. ADB sideload is
   not supported by this two-file method.
4. Only reboot System after **`Installation and block-device readback passed.`**

There is **no selectable-format menu, automatic userdata format or
repartitioning**. Required capacity is at least **5700 MiB System** and
**1100 MiB Vendor**, with matching boot-related capacities. Larger existing
System/Vendor partitions are not shrunk; arbitrary repartitioned layouts are
not universally approved. Do not use PIT/Re-Partition to bypass rejection.

## What changes and what stays

Full System/Vendor/Boot/DTB/DTBO/vbmeta images are written and checked by
readback. The old system camera and libraries are replaced with the packaged
versions. Personal photos, application preferences, separate `/data/app`
updates and Magisk modules are not deleted; such overrides can still shadow
packaged applications.

On a preflight model/source/mount/capacity/checksum failure, stop and keep the
recovery log; writing does not follow that rejection. On a write/readback
failure, restore the matching backup before booting or retrying. Older TWRP
failing to decrypt newer FBE after Android boots normally is not a reason to
format again.

## Validation status

All three model images and packages passed host capacity, packed-content,
owner/mode/SELinux, EROFS/read-only ext4, full-ZIP hash, all 36 payload-chunk,
source-contract and launcher checks. Focused recovery fixtures/regressions passed.

**Physical full-ZIP clean-install/original-beta-upgrade and S10e/S10+ acceptance
remain pending.** Reference G973F runtime checks used a narrower system-only
image, not this family ZIP. Calls/two-way audio, Bluetooth accessories,
HDMI/DeX, all camera modes, long-term OC/undervolt stability and broad AI
functionality are not universally accepted. Stable is the maintainer's release
channel, not a claim that these tests were completed.

Read your model's `VALIDATION.json` and the [release notes](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/RELEASE_NOTES.md).
For bug reports, include the exact model, source firmware/ROM, installation
path, error and recovery log. Remove IMEIs, serial numbers and personal data
before posting logs publicly.
