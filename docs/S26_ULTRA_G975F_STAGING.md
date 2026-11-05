# SM-G975F — S26 Ultra System staging

This is the firmware-tree adaptation stage, NOT a finished port/installer.

Use publicly distributed Samsung **SM-S948B** One UI 9 / Android 17
firmware that has been independently verified and extracted into a root-
preserving merged System tree. **One UI 9.5 remains unavailable publicly as
of 2026-11-05**. No S26 Ultra modem/bootloader/vendor may be flashed to S10+.

## Inputs

- `--donor`: `input.json` with verified system image checksum,
  model `SM-S948B`, build `S948BXXU5BZJA`, and `tree/system`
  with complete `product/` and `system_ext/` folders. The existing
  SM-S942B donor does NOT satisfy these requirements.
- `--stock`: registered `SM-G975F` original stock firmware extracted with
  owner, SELinux xattrs and complete images; use
  `s10_models.verify_family_stock` to establish provenance.
- `--kernel`: built model-specific S10+ boot/DTB/DTBO and manifest from
  `build_oneui9_s10_kernel.py --model SM-G975F`.
- `--display-bundle`: output of `s10_display_defaults.build` containing
  the reviewed dual-camera cutout geometry and compiled services.
- `--output`: new empty candidate destination with an existing parent.

The script copies the *whole* S26 Ultra System, retains the modern signed
Samsung Camera, carries over the G975F vendor, applies original hardware
floating features, and installs original camera-native compatibility libraries
only if they do not collide with donor versions. GMS/GSF/Play Store absence
causes a hard error rather than silently shipping a broken image.

```sh
sudo python3 scripts/astropart_s26_port.py \
  --donor /path/to/verified-s948b \
  --stock /path/to/verified-g975f \
  --kernel /path/to/built-g975f-kernel \
  --display-bundle /path/to/compiled-display \
  --output /path/to/new-astropart-tree
```

**This candidate is explicitly marked `ready_for_installation=false`.**
System/Vendor SELinux policy compilation, VINTF matrix reconciliation,
SystemUI execution, camera interfaces, original Snapdragon donor framework
adaptation, GMS runtime, AI packages, full image build, measured size and
safe install/rollback still need completion and physical acceptance.

The proposed System 10,240 MiB and Vendor 2,048 MiB are budget estimates,
**not** partition definitions or permission to repartition. Preserve
the original PIT until actual images and a tested recovery/rollback path exist.
