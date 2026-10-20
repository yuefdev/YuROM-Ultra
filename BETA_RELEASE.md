# YuROM Ultra V35 Beta packaging

The Beta distribution uses `v35-beta` package manifests and filenames
`YuROM_Ultra_OneUI9_v35_BETA_<MODEL>_TWRP.zip` and
`YuROM_Ultra_OneUI9_v35_BETA_<MODEL>_INSTALLER_r4.zip`.

The system/vendor/boot/device-tree/AVB image bytes are retained from the verified
V35 payloads. The runtime's existing telemetry build identifier is a compatibility
identifier; the distribution channel is Beta. Container manifests, installation
text, checksums and the exact-name launcher are regenerated together.

## Build

Prepare the matching candidate images and pinned stock/kernel/AVB inputs with
the maintained tools under `scripts/`. Then run `scripts/build_s10_twrp.py`
with `--version v35-beta`, the matching candidate, boot, kernel and AVB paths,
a fresh output ZIP and an external records directory. Generate its launcher
with `scripts/build_s10_twrp_bootstrap.py`. Assemble all three model records
with `scripts/assemble_s10_public_test.py --version v35-beta`.

The payload builder hashes every source image, writes 1 GiB image chunks with
bounded-memory streaming, reads every packed chunk back and pins the launcher
to the exact payload filename and complete SHA-256.

## GitHub download parts

GitHub limits individual release assets to 2 GiB; each full payload exceeds
4 GiB. Download all numbered parts for one model, its small installer,
`DOWNLOADS.json` and `join_yurom_beta.py` into the same directory.

With Python 3.11 or newer, run:

```sh
python join_yurom_beta.py SM-G973F
```

Choose `SM-G970F` or `SM-G975F` instead for those models. The helper checks the
small installer, each part and the complete reconstructed payload. It leaves
the downloaded parts intact and refuses to overwrite another existing payload.
Provide enough free space for both the downloaded parts and reconstructed ZIP.
The numbered transport parts themselves are not flashable.

Keep the final full ZIP and exact matching small installer together on exFAT
storage or on storage populated after Format Data. Follow the release's
installation instructions and select the small installer in TWRP.
**Format Data deletes apps, accounts and internal storage.** Back up first.
ADB sideload is unsupported by this two-file method.

## Validation

`scripts/tests/test_s10_public_release.py` covers Beta assembly, legacy channel
compatibility, full-file checksums, part reconstruction, corrupt-part cleanup,
existing-file preservation and bounded chunk packing.

`scripts/tests/test_s10_twrp.py` exercises rejection and write/readback cases
against temporary loop devices, including the real ARM64 recovery tools under
QEMU. These fixtures do not replace physical device acceptance.

The recorded reference S10 acceptance covers exact system-image readback,
normal boot, encrypted userdata access and both Settings GitHub links. A prior
native clean installation used V32. The full V35 Beta ZIP has not been
clean-installed on a phone; S10e/S10+ physical validation remains pending.
SELinux is Permissive in the accepted device configuration.
