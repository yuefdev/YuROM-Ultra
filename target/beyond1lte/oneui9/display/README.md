# S10-family display defaults

The model registry is `profiles.json`. Its cutout paths match each model's
Samsung HWC1/HWC2 vendor RRO and the corresponding
[ExtremeROM target overlays](https://github.com/ExtremeXT/ExtremeROM/tree/2056320784b7d1d88f9e7025f86f7bbd39945d6b/target).
LineageOS beyond0lte/beyond2lte configurations independently confirm the
single-camera versus wider dual-camera exclusion areas.

| Model | Native panel | First-install mode | Density | Portrait indicator inset |
|---|---|---|---|---|
| SM-G970F | 1080×2280 | 1080×2280, 60 Hz | 480 dpi | 56 dp |
| SM-G973F | 1440×3040 | 1080×2280, 60 Hz | 420 dpi | 64 dp |
| SM-G975F | 1440×3040 | 1080×2280, 60 Hz | 420 dpi | 100 dp |

The donor's indicator layout needs a portrait inset that reserves the camera
width. Insets round the model cutout width upwards with at least 6 dp clearance.
S10e/S10+ values remain subject to physical model acceptance.

The native display preference is seeded only when none exists. Density is
provided by the model's preserved vendor properties. The first-install marker
prevents overwriting later user display and overlay choices. All code and
configuration required to recreate these settings after Format Data live in
the ROM system image.
