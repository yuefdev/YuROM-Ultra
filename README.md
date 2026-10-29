<div align="center">
  <h1>YuROM Ultra</h1>
  <p><strong>One UI, your way.</strong></p>
  <p>A new chapter for the Exynos Galaxy S10e, S10 and S10+.</p>
  <p>
    <a href="https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-r32"><img src="https://img.shields.io/badge/V35_R32-Stable-238636?style=for-the-badge" alt="V35 R32 — Stable release channel"></a>
    <img src="https://img.shields.io/badge/One_UI-9-2563eb?style=for-the-badge" alt="One UI 9">
    <img src="https://img.shields.io/badge/Android-17-3DDC84?style=for-the-badge&logo=android&logoColor=white" alt="Android 17">
    <a href="LICENSE"><img src="https://img.shields.io/badge/Licence-GPLv3-64748b?style=for-the-badge" alt="GNU GPL version 3"></a>
  </p>
  <p>
    <a href="https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-r32"><strong>Download R32</strong></a>
    &nbsp;·&nbsp; <a href="RELEASE.md"><strong>Installation guide</strong></a>
    &nbsp;·&nbsp; <a href="https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/RELEASE_NOTES.md">Release notes</a>
    &nbsp;·&nbsp; <a href="https://xdaforums.com/t/4805709/">XDA discussion</a>
  </p>
</div>

---

## Familiar Samsung software. More room to make it yours.

YuROM Ultra brings **One UI 9 / Android 17** to the Exynos S10 family, based on
donor build `S942BXXU4ZZH6`. Model-specific hardware packages and native YuROM
controls keep the Samsung experience at the centre.

| What you get | In the ROM |
| --- | --- |
| **Built-in controls** | YuROM options inside Samsung Settings: launcher, status bar, lock screen and per-app customisation. |
| **Adaptive tuning** | Load-aware CPU/GPU controls with thermal limits and rollback; no guaranteed benchmark or battery-life claims. |
| **Model-specific packages** | Separate vendor, boot and device-tree inputs for each supported Exynos model. |
| **Samsung apps retained** | Video Library, Interpreter, Calendar, Calculator, Good Lock and Device Care. |
| **Compatibility work** | Camera/native-library, WebView, Themes, Eye Comfort and media repairs. |
| **One ROM per model** | The same full payload for fresh userdata and verified original-beta upgrades, with preflight and readback checks. |

## What's new in R32

- Updated Samsung camera integration and native compatibility repairs.
- Dual-ABI WebView repair, including the Samsung Account web flow.
- Bluetooth PCM/audio-policy and Galaxy Themes startup repairs.
- Enforcing init restoration and narrowly scoped real-TEE PDE storage repair.
- A naturally scheduled Now Brief lock-screen card and normal tap navigation
  checked on the reference S10; this is **not** blanket Galaxy AI acceptance.

[Read the changes and their validation limits →](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/RELEASE_NOTES.md)

## Choose your exact device

| Device | Model | Codename | Package checks |
| --- | --- | --- | --- |
| Galaxy S10e | **SM-G970F** | `beyond0lte` | [Validation](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/SM-G970F_VALIDATION.json) |
| Galaxy S10 | **SM-G973F** | `beyond1lte` | [Validation](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/SM-G973F_VALIDATION.json) |
| Galaxy S10+ | **SM-G975F** | `beyond2lte` | [Validation](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/SM-G975F_VALIDATION.json) |

**Exynos only.** Not for Snapdragon devices, Korean N variants or the S10 5G.

## Download and install

1. Open the **[R32 release](https://github.com/yuefdev/YuROM-Ultra/releases/tag/v35-r32)**
   and download your model's three transport pieces, matching
   `INSTALLER_r1.zip`, `DOWNLOADS.json` and `join_yurom.py`.
2. With **Python 3.11+**, reconstruct and verify the full ROM. For an S10:

   ```sh
   python join_yurom.py SM-G973F
   ```

3. Keep the resulting **full ROM ZIP + matching small installer** together.
   In compatible model-specific TWRP, flash the **small installer**, not a
   numbered piece or the large ZIP64 ROM.

Read **[the installation guide](RELEASE.md)** first. Only the exact original,
model-specific `v35-beta` six-image set supports the data-preserving upgrade.
Changed source boot/root, other releases and partial flashes are rejected.
**Do not format for that verified upgrade.** There is no automatic format or
format-selection menu, and no repartitioning.

> **Before you flash:** Stable is the maintainer's release channel. The full R32
> ZIP's physical clean-install/original-beta-upgrade checks and S10e/S10+
> physical acceptance remain pending. Reference S10 runtime checks used a
> narrower system-only image, not this full family ZIP. Back up externally.

## Source, transparency and credits

- **[ROM source baseline](https://github.com/yuefdev/YuROM-Ultra/tree/f3642b7353c28227a478c8f45e9b860727b02d99)**
  and [S10 port/build inputs](target/beyond1lte/oneui9/README.md).
- **[Focused R32 installer/native-compatibility sources](https://github.com/yuefdev/YuROM-Ultra/releases/download/v35-r32/YuROM_Ultra_V35_R32_Installer_Source.zip)**.
  The baseline and automatic tag archive are **not** a complete committed R32
  source snapshot. This landing-page update changes documentation only.
- **[Corresponding unchanged kernel source and exact model configs](https://github.com/yuefdev/YuROM-Ultra-kernel/tree/47d8fbc79c77e05686cb0926f1f66f16a94bd6d9)**.
  Packaged Magisk 30.7 derivations preserve those kernel/FBE inputs.
- **[GNU GPL v3](LICENSE)**; external components retain their respective licences.

Thanks to **XGSI, ArtisanROM/UN1CA, ExtremeXT/ExtremeROM, LineageOS, Samsung,
Team Win/TWRP, EROFS, Android, kernel contributors and testers**. Original
provenance and detailed upstream credits are preserved below; their historical
feature list is not a validation claim for this S10 release.

---
<details>
<summary>Historical upstream ArtisanROM build-system documentation</summary>

<h1 align="center">
  <img loading="lazy" src="readme-res/banner.png"/>
</h1>
<p align="center">
  <a href="https://github.com/ArtisanROM/ArtisanROM/blob/sixteen/LICENSE"><img loading="lazy" src="https://img.shields.io/github/license/ArtisanROM/ArtisanROM?style=for-the-badge&logo=github"/></a>
  <a href="https://github.com/ArtisanROM/ArtisanROM/commits/sixteen"><img loading="lazy" src="https://img.shields.io/github/last-commit/ArtisanROM/ArtisanROM/sixteen?style=for-the-badge"/></a>
  <a href="https://github.com/ArtisanROM/ArtisanROM/stargazers"><img loading="lazy" src="https://img.shields.io/github/stars/ArtisanROM/ArtisanROM?style=for-the-badge"/></a>
</p>
<p align="center">ArtisanROM <i>Quant</i> is a work-in-progress custom firmware for Samsung Galaxy devices.</p>

<p align="center">
  <a href="https://github.com/ArtisanROM/ArtisanROM/issues">🚀 issues</a>
  •
  <a href="https://discord.gg/TxYWApVRaE">💬 Discord</a>
  •
  <a  href="https://github.com/ArtisanROM/ArtisanROM/wiki">📖 Wiki</a>
  •
  <a href="https://github.com/ArtisanROM/ArtisanROM/blob/sixteen/CHANGELOG.md">📝 Changelog</a>
  •
  <a href="https://github.com/ArtisanROM/ArtisanROM/blob/sixteen/MAINTAINERS">🧑‍💻 Maintainers</a>
</p>

# What is ArtisanROM Quant?
ArtisanROM Quant is a work-in-progress custom firmware for Samsung Galaxy devices.

It's based on the latest and greatest iteration of Samsung's UX and it also includes additional features and tweaks to ensure the best possible experience out of the box.

It is based on the UN1CA build system which allows automatic downloading/extraction of the firmware, applying the required patches and generating a flashable zip package for the specified target device.

ArtisanROM Quant supports devices using the Exynos 990 SoC

Any form of contribution, suggestions, bug report or feature request for the project will be welcome.

# Features
### Core features:
- Based on the latest stable Galaxy S22 firmware
- EROFS powered
- Galaxy S25 wallpapers/sounds included
- Galaxy AI support
  - Audio eraser
  - Browsing assist
  - Call assist
  - Drawing assist
  - Interpreter
  - Note assist
  - Now brief
  - Photo assist
  - Semantic search
  - Transcript assist
  - Writing assist
- High end animations
- Native/live blur support
- AOD clock transition support
- Adaptive color tone support
- Adaptive refresh rate support(HFR WIP)
- Extra brightness support
- Picture remaster support
- Object, shadow and reflection eraser support
- Image clipper support
- Multi user support
- Samsung DeX support*
- Camera privacy toggle support
- Debloated from useless system services/additional apps
- Dual Messenger available for all apps
- Custom FlipFont fonts support
- Outdoor mode support
- Auto PIN confirm with 4 digits
- [BluetoothLibraryPatcher](https://github.com/3arthur6/BluetoothLibraryPatcher) integrated
- [KnoxPatch](https://github.com/salvogiangri/KnoxPatch) integrated
- Extra CSC features enabled (Call recording, Hiya, Network speed in status bar, AltZLife)

\* DeX via HDMI not available for devices without USB-C DP support

### ArtisanROM-exclusive features:
- Integrated OTA updates app
- Completely upstreamed kernels*

\* Exynos990

### UN1CA-exclusive features:
- Native/live blur toggle
- One UI Home animations option
- Vulkan renderer toggle
- Key attestation spoof ([TrickyStore](https://github.com/5ec1cff/TrickyStore)) options*
- Play Integrity Fix integrated
- Ability to hide installed apps ([Hide My Applist](https://github.com/Dr-TSNG/Hide-My-Applist))
- Ability to hide developer options
- Allow app downgrade toggle
- Allow installing apps with old targetSdk toggle
- Allow secure screenshot toggle
- Screenshot/screen recording detection toggle
- Unlimited backup storage on Google Photos
- Games FPS unlock toggle

\* Requires a valid keybox

# Licensing
This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE). External dependencies might be distributed under a different license, such as:
- [android-tools](https://github.com/nmeum/android-tools), licensed under the [Apache License 2.0](https://github.com/nmeum/android-tools/blob/master/LICENSE)
- [apktool](https://github.com/iBotPeaches/Apktool), licensed under the [Apache License 2.0](https://github.com/iBotPeaches/Apktool/blob/master/LICENSE.md)
- [erofs-utils](https://github.com/sekaiacg/erofs-utils/), dual license ([GPL-2.0](https://github.com/sekaiacg/erofs-utils/blob/dev/LICENSES/GPL-2.0), [Apache-2.0](https://github.com/sekaiacg/erofs-utils/blob/dev/LICENSES/Apache-2.0))
- [img2sdat](https://github.com/xpirt/img2sdat), licensed under the [MIT License](https://github.com/xpirt/img2sdat/blob/master/LICENSE)
- [platform_build](https://android.googlesource.com/platform/build/) (ext4_utils, f2fs_utils, signapk), licensed under the [Apache License 2.0](https://source.android.com/docs/setup/about/licenses)

# Disclaimer

```cpp
#include <std_disclaimer.h>

/*
* Your warranty is now void.
*
* I am not responsible for bricked devices, dead SD cards,
* thermonuclear war, or you getting fired because the alarm app failed. Please
* do some research if you have any concerns about doing this to your device
* YOU are choosing to make these modifications, and if
* you point the finger at me for messing up your device, I will laugh at you.
*
* I am also not responsible for you getting in trouble for using any of the
* features in this ROM, including but not limited to Call Recording, secure
* flag removal etc.
*/
```

- You are not allowed to modify or redistribute this ROM without prior approval

# Contributors
<a href="https://github.com/ArtisanROM/ArtisanROM/graphs/contributors"><img loading="lazy" src="https://contrib.rocks/image?repo=ArtisanROM/ArtisanROM"/></a>

# Credits:
- **[salvogiangri](https://github.com/salvogiangri)** for the UN1CA build system, OneUI patches, and general help and support while developing.
- **[ExtremeXT](https://github.com/ExtremeXT)** for helping me fix bugs and giving me support.
- **[GhasemzadehFard-Dev](https://github.com/GhasemzadehFard-Dev)** for helping fix many bugs I was not able to fix.
- **[Mesazane](https://github.com/Mesazane)** for testing and helping with the updaters design, and for updating and fixing KernelSU-Next on the Kernels.
- **[ricci205GTI](https://github.com/ricci205GTI)** for fixing motion photo and help with the x1s.
- **[immohammeeed](https://github.com/immohammeeed)** for creating the website for this project.
- **[3q5i](https://github.com/3q5i)** for support and ideas for the ROM.
- **[irvinhaha](https://github.com/irvinhaha)** for designing many banners and logos
- **[CiprianDinca](https://github.com/CiprianDinca9)** for custom ExtremeROM ringtones
- **[Dupazlasu/Milxnaq](https://github.com/milxnaq)** for fixing bluetooth on the S10x and much more
- More that I can't remember right now and will have to be added in the future

## Original UN1CA credits:
A special thanks goes to the following for their invaluable contributions in no particular order:
- **[ShaDisNX255](https://github.com/ShaDisNX255)** for his help, time and for his [NcX ROM](https://github.com/ShaDisNX255/NcX_Stock) which inspired this project
- **[DavidArsene](https://github.com/DavidArsene)** for his help and time
- **[paulowesll](https://github.com/paulowesll)** for his help and support
- **[Simon1511](https://github.com/Simon1511)** for his support and some of the device-specific patches
- **[ananjaser1211](https://github.com/ananjaser1211)** for troubleshooting and his time
- **[Fede2782](https://github.com/Fede2782)** for his contributions and help with Exynos/MTK support
- **[iDrinkCoffee](https://github.com/iDrinkCoffee-TG)** and **[RisenID](https://github.com/RisenID)** for their support
- **[LineageOS Team](https://www.lineageos.org/)** for their original [OTA updater implementation](https://github.com/LineageOS/android_packages_apps_Updater)
- *All the UN1CA project forks, contributors, testers and users ❤️*

# ArtisanROM Archive
- [ArtisanROM Archive Org](https://github.com/ArtisanROM-archive)
- [Old Sixteen branch](https://github.com/ArtisanROM-archive/ArtisanROM_old)

</details>
