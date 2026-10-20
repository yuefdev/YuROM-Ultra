# Experimental One UI 9 S10 target

This separate target uses the pinned `S942BXXU4ZZH6` XGSI donor, original
`SM-G973F` HWC1 vendor inputs and the stock partition layout in
`stock-layout.json`. It is not an extension of the existing repartitioned
One UI 8 installer. It must not use that installer's partition contract.

## Inputs and kernel

Import verified archives with `scripts/prepare_oneui9_inputs.py`. New output
directories are required. Linux root preserves Android ownership, modes and
SELinux xattrs through read-only image mounts.

The experimental kernel uses commit
`a97afb2c431802523a89fb875a3faadb7dcaac26` from
`https://github.com/ArtisanRomS10/android_kernel_samsung_exynos9820.git`.
The netlink-xperm backport adapts upstream Linux commit
`d1d991efaf34606d500dcbd28bedc0666eeec8e2`. Capability index 9 must match
libsepol. Unsupported capability indices 6-8 are not exposed in selinuxfs.

The kernel also restores the functional Android `SECURITY_PERF_EVENTS_RESTRICT`
backport from common-kernel commit `6954d981214c6cd0658eea10857a0f0ab7440e29`.
It defaults perf paranoia to 3 and rejects unprivileged `perf_event_open` access
while retaining existing SELinux checks. The S10 configuration enables it;
the stock FCM kernel contract must pass without removing this requirement.

`scripts/build_oneui9_s10_kernel.py` records the actual source diff, configuration,
toolchain and image checksums. It retains ext4 and quota but changes userdata
from the unsupported private ICE mode 127 to `aes-256-xts:aes-256-cts:v2` in both
ramdisk and vendor fstabs. File-based encryption remains enabled. This transition
requires a separately authorised clean data installation; never reuse existing
encryption keys or silently wipe data. Rollback restores matching verified
boot/vendor images, not the discarded userdata. Auxiliary partitions absent
from the stock S10 layout are omitted.
The existing cache mounts in first stage. The candidate binds
`/cache/oneui9-metadata` at `/metadata` before the donor flag-storage daemon starts.
Both paths retain matching metadata SELinux labels. Cache now contains persistent
Android metadata; clearing it also removes that state. No partition is added or
resized, and existing feature flags are retained.

For the live display adaptation, compile `scripts/android/S10DisplayOverlay.java`
with Android D8 and run its DEX through root `app_process`. It registers
`android:S10DisplayGeometry`: the maintained right-camera cutout plus a typed
64 dp portrait indicator inset. Framework ownership retains the overlay across
reboots; shell-owned diagnostic overlays may be discarded. Disable it with
`cmd overlay disable --user 0 android:S10DisplayGeometry` to roll back.
Select the panel's native FHD+ mode with
`cmd display set-user-preferred-display-mode 1080 2280 60 0 true`.
This keeps ordinary animation scales and blur effects; it does not require
changing SystemUI's APK or signing certificate.

The Android Clang r547379 archive is bound to the verified official Git tree
`a86cb6592a29d53254d3a88ff2d8282233a273e2`. Gitiles archive bytes can differ
between downloads; do not change an archive checksum without verifying all
contents, executable modes, symlink targets and directory Git objects.

Run the focused kernel regression check:

```sh
python3 -B scripts/tests/test_s10_netlink_xperm.py --kernel ../s10-kernel
```

This executes the actual xperm aggregation functions for NLMSG permission scope,
driver filtering, audit decisions and preserved IOCTL handling. It does not
prove kernel policy loading or device enforcement.

## Candidate and validation

`scripts/prepare_oneui9_s10_candidate.py` creates a merged system and a separate
original-HWC1-based vendor candidate. It restores FCM levels 3-6, preserves
selected stock camera/audio inputs and reuses the maintained Exynos 9820 HIDL 6
audio wrappers and matched service. Original HWC1 inputs remain the rollback
source. Older audio libraries are retained during the compatibility transition.

Extract legacy framework VINTF inputs with `scripts/prepare_s10_legacy_vintf_inputs.py`
(`--stock` and `--output`) and pass that cache as `--stock-vintf` to the candidate
preparer. The original level-independent HWC1 matrix supplies SELinux compatibility;
the original VNDK 31 declaration is retained as a framework manifest fragment.
The donor must provide the VNDK 31 APEX. These declarations do not prove runtime HAL
registration or linker compatibility.

The combined policy uses binary version 31. Compilation with Android init's
normal mixed-version flags (`-m -M true -G -N`) does not disable SELinux
enforcement. A separate strict neverallow check is archived for investigation.
No permissive domains are accepted.

The candidate retains HWC1 ownership of the Widevine service property context.
Its checksum-pinned system `libui.so` patch enables the existing mapper 3/2
fallback after mapper 5/4 fail, including compiler-inlined construction and HAL
preload paths, without changing the reported Android SDK.
SurfaceFlinger uses the donor-supported `skiaglthreaded` backend. HWC1 vendor
init owns the Samsung USB gadget; the donor USB override only selects the S10
controller. Vendor graphics libraries, APEX payloads and secure ADB are preserved.

The S10 kernel and HWC1 power configuration use legacy SchedTune rather than
the donor's uclamp interface. `scripts/s10_schedtune.py` adds vendor-only cgroup
and task-profile overrides plus early init groups. Foreground/top-app groups
retain HWC1's utilisation estimation, on-time migration and top-app boost of 5.
The donor's CPU, cpuset and I/O actions are preserved; framework app-state
transitions move tasks between the groups. This does not change clock limits.
Run `scripts/tests/test_s10_schedtune.py --system <candidate>/tree/system
--stock-vendor <stock>/vendor` to check profile preservation and transitions.

The pinned native zygote enumerates capabilities newer than the Linux 4.14
kernel implements. `scripts/s10_native_zygote.py` restricts its existing drop-set
to capabilities 0-37, matching `cap_last_cap`, using one checksum-guarded ARM64
instruction. All supported capability drops and whitelist handling remain.
A vendor init binding activates the isolated library before native zygote starts.
Run `scripts/tests/test_s10_native_zygote.py --system <candidate>/tree/system`
to verify the actual mask, supported drops and unknown-input rejection.

The checksum-pinned GPU806 kernel also has a vendor oneshot performance service.
After `sys.boot_completed=1`, it requests CPU ceilings of 2106/2400/3016 MHz,
an 806 MHz GPU ceiling, -3% CPU/GPU voltage margins and 1 ms LITTLE/MID
schedutil up limits. Thermal and over-current limits can reduce effective clocks.
Other boot images are skipped. An interrupted application or Android restart
during the initial 30-second observation disables subsequent automatic attempts.
Use `sh /vendor/etc/s10-performance-profile.sh disable` to disable automatic
application and restore normal margins/clocks; `enable` explicitly re-enables it.
The script is independent of diagnostic files and does not alter charging.
Run `python3 -B scripts/tests/test_s10_boot_performance.py` for the focused
application, wrong-kernel, interrupted-boot and rollback checks. Live permissive
boot validation does not establish enforcing-policy compatibility.

With Unicorn 2.1.4 installed in the test environment, run:

```sh
python3 -B scripts/tests/test_s10_legacy_mapper.py --original-system <unpatched-candidate>/tree/system
```

This executes the actual ARM64 and Thumb SDK-gate instructions before and after
patching. It verifies fallback control flow and rejects unknown donor binaries;
it does not prove graphics HAL loading, APEX mapper compatibility or display output.

The swcodec APEX contains a separate ARM64 `libui.so` with the same SDK gate.
`configure_swcodec_and_hwui` extracts the checksum-pinned donor library and stages
only its three mapper fallback instructions under `lib64/s10-swcodec`. Init binds
that copy over the module's library after full APEX activation and before zygote
or core services start. The signed APEX archive and global system libraries stay
intact. Revalidate the overlay when updating the swcodec APEX. HWUI defaults to
`skiagl` for the legacy Mali driver; application Vulkan APIs remain available.

Pass `--original-swcodec-libui <original-module-libui.so>` to the mapper test to
execute the module's constructor, inlined and preload gates too. The focused
device probe in `scripts/android/S10SoftwareDecodeProbe.java` accepts a short
video fixture and `buffer` or `surface` output, selects a software decoder, and
requires decoded frames and end-of-stream. Live decoder checks do not prove the
new init mount's cold-boot ordering or enforcing-policy compatibility.

`scripts/make_oneui9_s10_images.py` packs legacy LZ4 EROFS system and ext4 vendor
images. It checks stock partition capacities, full decompression, read-only fsck,
selected file contents, Android ownership/modes and SELinux labels.

`scripts/check_oneui9_s10_native.py` inventories vendor executables and migrated
audio libraries against selected runtime/VNDK APEX providers. This does not
verify Android linker namespaces, symbol-version selection or runtime HAL
registration. Validation reports belong outside the checkout, as required by
`AGENTS.md`.

Build manifests retain `ready_for_installation: false`; a build alone does not
prove device boot or hardware support. `scripts/install_oneui9_s10.py` is the
explicit installation entry point. It requires the verified TWRP/AVB bootstrap,
independent raw rollback backups and actual donor linker/VINTF results. It
checks every uploaded image and raw write by SHA-256, uses the original partition
layout and leaves reboot to a separate step. `--format-data` irreversibly deletes
all internal user data after verified image writes. Runtime HAL registration
and hardware operation still require an actual boot test.

## Settings signature

The candidate preparer calls `scripts/s10_settings_branding.py` to install a
code-free, mutable system_ext resource overlay. It preserves the pinned Settings
APK and all thirteen Software information controllers. A compile-only symbol
library keeps OEM resource imports distinct from overlay-local IDs. The original
preload allowlist gains one package; existing entries and notices are retained.
Android 36 build tools must be prepared under `out/host-tools/android-sdk-36`.

The card uses the author's Riftroam black-hole scene and palette. Its maintained
WebP frames are required build inputs. Native drawable playback stops off-screen;
tapping the card changes visual contrast. Regenerate frames with a Chromium-based
browser, then run the focused compiled-resource check:

```sh
node scripts/render_s10_blackhole.mjs --browser <chromium-executable> --output <new-frame-directory>
python3 -B scripts/tests/test_s10_settings_branding.py --system <candidate>/tree/system
```

Replace `settings-branding/res/drawable-nodpi` with the regenerated frame directory
before rebuilding. Disable the overlay persistently with
`cmd overlay disable --user 0 com.artisanrom.s10.settings.signature`.
