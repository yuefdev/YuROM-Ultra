# Artisan Control

Native **Settings → Artisan** preferences, a shared `ac_*` settings contract,
framework hooks and checksum-pinned OEM adapters. The first adapter supports the
maintained One UI 9 Settings APK and Honeyspace launcher. There is no standalone
control APK. A different ROM requires an adapter for its actual binaries.

## Controls

- Per-app secure screenshots/recording, capture-callback suppression, developer/ADB
  status visibility, package-list filtering and device identity profiles.
- Lock-screen battery watts, volts, current and temperature, configurable refresh,
  Flow/Wave connection effects, unseen notifications, inline replies and fingerprint
  haptics.
- Privacy indicators, notification sounds with the screen on, first-notification
  expansion, incoming-call presentation, notification history and category controls.
- Screen-off volume-key media controls, screen timeout and extended power menu.
- Clock/date/colour/size, network speed and status-icon visibility.
- Home/apps grids through 7×9, dock count, endless paging, icon size/labels/packs,
  recents layouts/card geometry/circular effects, animation timing/bounce, gestures
  and folders.
- JSON settings export/import and version-matched launcher layout backup/restore.

## Build

Prepare Android 36 build tools, Java, Python, smali and baksmali. Use a fresh output
directory and external records directory:

```sh
python3 -B scripts/build_artisan_control.py \
  --system <prepared-system> \
  --adapter packages/ArtisanControl/adapters/oneui9.py \
  --build-tools <build-tools> --android-jar <android.jar> \
  --output <new-bundle> --records <external-records>
python3 -B scripts/tests/test_artisan_control.py
```

The builder rejects unknown input hashes, retains OEM method bodies and certificate
identity, and preserves every existing Settings resource, manifest and preference
controller. Native fragments and their catalogue are appended to the Settings APK.
Compilation-only stubs describe pinned Samsung/AndroidX APIs and never ship in the
APK. Modified OEM content digests are invalid: these are preinstalled ROM inputs,
not independently signed Package Installer updates.

## ROM integration

Pass `--artisan-control <bundle>` to `prepare_oneui9_s10_candidate.py`, or run:

```sh
python3 -B scripts/artisan_control.py \
  --system <prepared-system> --vendor <prepared-vendor> --bundle <bundle>
```

This installs matched framework/SystemUI/Home/Settings binaries, a peer-UID checked
root broker and its init definition. The Settings homepage opens a genuine
`SettingsPreferenceFragment` hosted by `com.android.settings.SubSettings`.
Kernel, performance scripts and existing Samsung preload entries are retained.
An enforcing ROM needs a separately validated broker/socket SELinux policy; the
live S10 integration currently targets its existing permissive configuration.

## Live trial and rollback

```sh
python3 scripts/install_artisan_control.py --adb <adb> --serial <serial> \
  --bundle <bundle> --records <new-external-records>
python3 scripts/persist_artisan_control.py --adb <adb> --serial <serial> \
  --bundle <bundle> --records <new-external-records>
```

The trial stages original files and installs temporary bind mounts. Its watchdog
restores originals if the UI fails to start. Persistence is a separate step with
read-back checks and a boot watchdog. Disable persistent hooks and reboot with:

```sh
adb shell sh /vendor/etc/artisan-control/disable.sh
```

During a temporary trial, use
`adb shell sh /data/system/artisan-control/rollback.sh`.
Restoring original framework, services, SystemUI, Home and Settings together is required.
Temporary updates require `--previous-bundle <currently-mounted-bundle>`.
Permanent updates require `--previous-bundle <previous-permanent-bundle>` and matching
existing boot scripts. The installer pauses old boot mounts during the trial;
the persister archives previous scripts before replacing them. Earlier control-app
initial-value history is copied to the Settings preferences if not already present.
Existing `ac_*` values remain in their original settings namespaces. Let the boot-time
performance health window finish before starting another reboot test.

The pinned donor `vold` rejects legacy hardware-auth tokens in CE-storage unlock
requests. Its S10 adapter sends the existing empty-token sentinel at the storage
IPC boundary while retaining Gatekeeper verification and the synthetic-password
derived encryption secret. Secured users can therefore unlock their existing FBE
storage after reboot. The exact `vold` checksum is checked during build, install
and persistent mounting. The same compatibility patch is applied to ROM builds
without the optional Artisan controls. A trial is healthy only after user 0 reaches
`RUNNING_UNLOCKED`; boot completion alone is insufficient.

## Validation and behaviour

`scripts/tests/build_artisan_control_probe.py` builds an own-app secure surface,
notification/inline-reply fixture, silent media session and microphone acquisition
probe. It never reads or stores microphone samples. Add `--icon-pack` to build the
separate resource-only compiled-appfilter fixture. Both fixture builds require an
existing external records directory.

```sh
python scripts/tests/test_artisan_control_device.py \
  --adb <adb> --serial <serial> --probe <probe.apk> \
  --launcher-ui --icon-pack <icon-pack.apk> --records <new-external-records>
```

The focused regression checks scoped identity/visibility, secure capture, actual
6×9/7×9 drawer cells, recents transitions, icon replacement/restoration, live privacy
indicator updates, broker framing, traversal rejection and launcher restore.
UI options target the pinned Samsung adapter. Test settings, screen timeout,
microphone permission and launcher data are restored. Keep APKs, images, logs and
results in their designated build/records locations.

`build_native_settings_probe.py` builds a root `app_process` runner that drives the
actual Settings preference widgets. `test_native_settings_ui.py` tests all catalogue
entries, every choice, numeric endpoints and invalid values in isolated sessions;
it restores raw values and the original reset history afterwards. Power actions are
opened and cancelled by that UI gate, not executed. Use
`test_native_settings_bundle.py --system <original-system> --bundle <bundle>` for
the native APK/resource and fresh-tree installation gate.

`test_artisan_control_charging.py --adb <adb> --serial <serial>
--records <new-external-records>` checks actual charging-window positioning,
Flow/Wave frame changes, animation expiry with a long information-refresh interval,
and removal when the screen turns off. It resets battery simulation and restores
test settings afterwards. Simulated connection events do not establish physical
charger compatibility.

Samsung disables Home's endless paging while its media page is enabled; turn that
page off in the launcher first. The Samsung silent-status slot is `mute`, distinct
from `volume`. Notification history follows this donor's enabled-by-default native
setting when no explicit value is stored. The compatible `ac_recents_loop` key
controls Samsung's circular card effect in the vertical layout.

Secure surfaces and DRM-protected video are separate mechanisms. Device profiles
do not change panel refresh rate or provide attestation keys. Charging power is
measured at the battery. Work/private-profile challenges and device policy remain
in the inline-reply path. New display/launcher features default off; enable them
from **Settings → Artisan** and restart Home after launcher changes.

Hands-on acceptance is still required for real fingerprint authentication/haptics,
carrier calls, folder/paging/animation feel and recovery/download-mode entry and
return to Android. An own-app fixture does not establish those hardware and
interaction outcomes.
