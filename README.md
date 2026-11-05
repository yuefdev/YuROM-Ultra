<div align="center">

# Astropart

**A full-featured Samsung One UI port project for the Exynos Galaxy S10 family.**

[![Platform](https://img.shields.io/badge/Platform-Exynos%209820-27415b)](https://github.com/RectifyData/Astropart)
[![Base](https://img.shields.io/badge/Upstream-YuROM%20Ultra-536dfe)](https://github.com/yuefdev/YuROM-Ultra)
[![Development](https://img.shields.io/badge/Status-Development%20%2F%20Not%20validated-orange)](https://github.com/RectifyData/Astropart)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue)](LICENSE)

</div>

> **Development source only — not a flashable release.** Astropart has not independently demonstrated a clean install, first boot, working telephony, or complete hardware functionality on any supported phone. Do not flash an unverified build, particularly on a device you cannot afford to lose.

## About

Astropart is a fork of [YuROM Ultra](https://github.com/yuefdev/YuROM-Ultra), built to preserve the complete Samsung experience on legacy Exynos 9820 hardware instead of removing apps to satisfy a small partition. The intended approach combines newer One UI components with *verified, model-matched* S10 hardware components and selective compatibility work from [ArtisanROM](https://github.com/ArtisanROM/ArtisanROM), its [older S10 port](https://github.com/ArtisanROM-archive/ArtisanROM_old), and [ExtremeROM](https://github.com/ExtremeXT/ExtremeROM).

**Current inherited source:** YuROM Ultra's One UI 9 / Android 17 port with donor build \`S942BXXU4ZZH6\`. **Target under investigation:** Galaxy S26 Ultra-derived system and Camera components, *not* a completed S26 Ultra firmware port. The existing donor must not be misrepresented as S26 Ultra.

The focus is **SM-G975F / beyond2lte (Galaxy S10+)** first. The inherited project also has model-specific inputs for **SM-G970F / beyond0lte** and **SM-G973F / beyond1lte**; neither should be treated as validated by work on another model. Snapdragon, S10 5G, and other unverified variants are not targets.

## Development goals

These are **goals and reported upstream issues**, not claims that Astropart has implemented or fixed them.

| Area | Planned work |
| --- | --- |
| Display and camera cutout | Correct S10+ dual-camera geometry, SystemUI spacing, service execution context and punch-hole animations; validate on actual hardware. |
| Google services | Diagnose repeated \`com.google.android.gms\` crashes; verify GMS, Google Services Framework, Play Store, permissions, signatures, provisioning and dependencies. |
| General stability | Fix reproducible framework, HAL, SELinux, graphics, connectivity, audio, power, camera and app crashes. |
| Root and kernel | Investigate a model-specific **KernelSU Next Legacy** integration with compatible **SUSFS**; do not ship an unbooted kernel. |
| App retention | **Remove automatic debloating scripts and module invocations** from the build after dependency and partition-size validation; retain Samsung/Google apps and required services. |
| Galaxy AI | Port only compatible, individually verified AI services and features, with honest limitations for on-device models and Samsung-account/region requirements. |
| Partitions | Develop an optional, recovery-aware S10+ repartitioning workflow from verified original PIT/layout evidence; preserve critical partitions and require explicit consent for any destructive operation. |
| Installer | Add visible, detailed installation progress, informative diagnostics and ASCII art; improve useful error messages. |
| Abort conditions | Remove unnecessary restrictions **without** disabling device identification, block-device capacity, image integrity, write/readback, backup or data-loss protections. |
| Camera application | Replace the inherited legacy Galaxy S10 Camera app only after adapting and verifying newer camera app/framework/native dependencies and all lenses. |
| Donor migration | Research an S26 Ultra system/framework donor while retaining correct Exynos 9820 kernel, vendor, radio, hardware HALs and device trees. |
| Regression testing | Add repeatable host tests, build checks and hardware acceptance gates for each specific device and release candidate. |

### No debloating means no silent removal

The desired shipping profile retains stock Samsung applications, Google components, language packs and feature dependencies wherever technically compatible. Upstream files such as \`unica/debloat.sh\`, \`unica/patches/_debloat/\` and platform-specific debloat lists are **present in the inherited source until actually removed in a code commit**. Deleting a script does not restore apps already absent from a donor image; those packages require source/provenance, version, signing and framework checks.

## Proposed partition budget (SM-G975F)

*Capacity proposals only, in MiB (1 MiB = 1,048,576 bytes). Not measured image sizes, partition-table definitions, or permission to repartition.*

| Partition | Planning capacity |
| --- | ---: |
| **System** | **10,240 MiB** |
| **Vendor** | **2,048 MiB** |
| Product (legacy partition, if retained) | 620 MiB |
| ODM | 4 MiB |
| PRISM | 600 MiB |
| OPTICS | 30 MiB |
| Boot | 55 MiB |
| Recovery | 64.5 MiB |
| DTB | 8 MiB |
| DTBO | 8 MiB |
| VBMeta | 0.0625 MiB |
| Cache | 600 MiB |
| System Ext | Merged into System |
| Super | Not used by this static-partition target |
| Userdata | Remaining space after a validated layout |

The inherited S10 source describes a **merged System/Product/System Ext installation**, so *logical content must not be double-counted*: the 10,240 MiB System estimate includes merged Product/System Ext data. The 620 MiB Product line only represents a possible retained legacy block partition. Any actual PIT change must account for all partitions, correct 4 KiB alignment, backup/restoration and available UFS capacity.

**No repartitioner is currently implemented or validated.** Before choosing a size, produce the final non-debloated images and compare their real filesystem sizes to the verified **SM-G975F** original and proposed layout. Keep the user's data and critical partitions safe.

## Compatibility and upstream reuse

- **Cutout:** ArtisanROM's archived \`target/beyond2lte/overlay/values/strings.xml\` provides the dual-camera cutout geometry; the inherited YuROM display profile already contains the same path. A wrong cutout on-device can therefore result from *overlay activation, resource priority, SystemUI spacing or recovery-time integration*, not necessarily the path.
- **SystemUI and Camera assets:** Compare the archived S10+ \`punch_hole_ic_b2\`, \`face_unlocking_cutout_ic_b2\`, and \`lottie_camera_punchcut_timer_b2\` resources with the newer donor's resource names before any adaptation.
- **Legacy vendor compatibility:** Inspect Exynos 9820-specific audio/camera native libraries, VNDK 31, permissions, VINTF declarations, init and SELinux policies. Do not blindly insert older binary patches into a different donor build.
- **Google services:** Determine exact package crash causes from logs rather than transplanting arbitrary GMS APKs; retain privileged permission XML and matching signatures.
- **Current hotfixes:** Review the *latest applicable upstream release and hotfix source* before reimplementing a change. Their published testing on one model does **not** validate the S10+.

## Project structure

| Path | Purpose |
| --- | --- |
| \`target/beyond1lte/\` | Inherited S10 hardware build inputs and model-family tooling |
| \`scripts/s10_models.py\` | Device registry, stock firmware identities and per-model partition reference |
| \`scripts/prepare_s10_family_candidate.py\` | Model-specific candidate integration |
| \`scripts/prepare_s10_samsung_camera.py\` | Legacy Samsung Camera compatibility code |
| \`target/beyond1lte/oneui9/display/\` | Per-model cutout profiles and one-time display service |
| \`target/beyond1lte/oneui9/installer/\` | Inherited recovery installer |
| \`unica/debloat.sh\`, \`unica/patches/_debloat/\` | Inherited automatic debloating (scheduled for removal) |
| \`scripts/tests/\` | Host-side regression and packaging tests |
| \`.github/workflows/\` | Inherited automation; a successful workflow is not proof of phone bootability |

## Build and test policy

1. Confirm exact donor and device-specific stock input provenance. Reject cross-model combinations.
2. Validate syntax, Python tests, shell scripts, XML/JSON, patches, partition/image sizes and ZIP packaging.
3. Validate SELinux labelling, VINTF/HAL dependencies, native library loading and installation rollback.
4. Run clean installation and boot acceptance on each specific model before describing a release as bootable or daily-driver suitable.
5. For hardware testing, cover camera lenses, calls/IMS/SMS/mobile data, Wi-Fi, Bluetooth, NFC, audio, GPU/display, sensors, charging, encryption and recovery.
6. Publish an experimental artifact only with accurate test scope, known failures, checksums and explicit **not safe to flash** labeling unless device-level acceptance exists.

**A green CI build is not a successful boot.** Do not disable meaningful integrity/safety checks to make an installer appear successful.

## Downloads and versioning

**Astropart has no verified installable release yet.** The upstream [YuROM Ultra releases](https://github.com/yuefdev/YuROM-Ultra/releases) belong to the original project; they are not Astropart builds or proof that this fork's changes have been tested. Do not mix an Astropart installer with upstream release image parts.

The starting branch in this fork is \`release/v35-beta\`. Upstream tags and release notes can be more recent than the source snapshot inherited here.

## Credits, source, licensing

Astropart is an independently maintained fork of [yuefdev/YuROM-Ultra](https://github.com/yuefdev/YuROM-Ultra). Credit and upstream source history belong to their respective contributors.

- [YuROM Ultra — original repository](https://github.com/yuefdev/YuROM-Ultra)
- [YuROM Ultra kernel sources](https://github.com/yuefdev/YuROM-Ultra-kernel)
- [ArtisanROM](https://github.com/ArtisanROM/ArtisanROM) and [archived S10 work](https://github.com/ArtisanROM-archive/ArtisanROM_old)
- [ExtremeROM](https://github.com/ExtremeXT/ExtremeROM)
- [UN1CA](https://github.com/salvogiangri/UN1CA)
- [Historical upstream README and acknowledgements](https://github.com/yuefdev/YuROM-Ultra/blob/release/v35-beta/README.md)

Project code is under the repository's [GPL-3.0](LICENSE) unless individual files specify other terms. Third-party artwork, Samsung/Google proprietary components, prebuilt firmware, and model assets may have separate redistribution restrictions; do not assume that an open-source build script grants permission to redistribute its inputs.

---

*Documentation describes the project direction and inherited source accurately as of 2026-11-05. Feature completion and physical validation must be tracked through actual changes and evidence.*
