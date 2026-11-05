# Astropart S10+ — implementation and acceptance gates

**Not a flashable release.** This branch is source work against the inherited
YuROM `release/v35-beta` build code, not a rebuild of the more recent R33 binary
releases. Physical bootability on SM-G975F remains unverified.

## User-requested 12 issue families

| Area | Source work | Unresolved acceptance |
| --- | --- | --- |
| 1. Camera cutout | Model S10+ path and display init context reviewed/fixed | On-device rotation, screenshots, status icons and Camera |
| 2. Google Play Services | Read-only package inventory preflight | Actual crash log diagnosis, certified GMS package and permission policy |
| 3. Abnormal framework behavior | Regression/syntax preflight | SELinux, boot, VINTF, thermal, audio, camera, NFC and connectivity |
| 4. KernelSU Next Legacy + SUSFS | Maintained as a kernel-source prerequisite | Build from correct Exynos 9820 kernel tree, boot, test mount, test SUSFS |
| 5. Over-debloating | Auto debloat lists/module deleted | Full Samsung/GMS apps absent from donor require separate packaging |
| 6. Galaxy AI | Development target retained | Verify capabilities and service dependencies one by one |
| 7. Repartitioner | Read-only size budget | Verified SM-G975F PIT and measured image sizes; no PIT writer yet |
| 8. Verbose installer/ASCII | Visible stages and recovery FD fix | Test in exact SM-G975F TWRP, no false success, no automatic data wipe |
| 9. Unnecessary installation aborts | Existing checks mapped | Determine false positives without bypassing device/size/image guards |
| 10. Broad bugs | Host checks and explicit pending report | Actual device logs and regression acceptance |
| 11. Desired S26 Ultra donor | Research + published S26 Ultra model/build reference | Signed firmware provenance and full framework/HAL adaptation |
| 12. Outdated Samsung Camera | Existing S10 native stack inspected | New Camera APK and all lens modes validated; old app still present |

## One UI 9.5

Samsung's public S26 Ultra SM-S948B update documentation shows Android 17 /
One UI 9 build `S948BXXU5BZJA` released 2026-10-29.
News on 2026-11-04 reported internal One UI 9.5 test
`S948BXXU6ZZK3` with upgraded bootloader U6; *not publicly available*
as an installable donor on 2026-11-05.
Do not invent a firmware URL, treat internal builds as public, or transplant
S26 Ultra bootloader, radio, vendor or boot images to an S10+.

References:
- https://doc.samsungmobile.com/SM-S948B/037115260310/por-br.html
- https://www.androidauthority.com/galaxy-s26-one-ui-9-5-beta-in-testing-3731840/

## Device evidence before release

- Back up userdata and EFS externally; never test first on the user's only
  device without a separately verified recovery/rollback path.
- Check that all required Android system, product and vendor APKs have compatible
  signatures/permissions; test Google Play Services from logcat, not just the
  presence of `com.google.android.gms`.
- Camera test: stock, ultrawide, telephoto, front, stills, HDR, autofocus,
  1080p and 4K video; verify original S10 drivers and camera IDs.
- Perform cold boot, unlock, encryption, calls, data, Wi-Fi, Bluetooth, NFC,
  GPS, graphics, sensors, charging and recovery acceptance.
- Require actual image sizes, filesystem labels and block partition sizes
  before approving a non-debloated merged System image or repartitioning.
- KernelSU Next and SUSFS are not integrated by an APK preload alone;
  obtain correct source/config/provenance and boot-test it.

The `scripts/astropart_audit.py` command is deliberately **read only**.
Never interpret a green host check as runtime acceptance.
