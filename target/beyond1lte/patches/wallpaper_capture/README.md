# Photo wallpaper capture fallback

DressRoom 2.9.10.42 can report object capture support while its native
ArcSoft engine fails to initialize on the S10. GetObjectProcess catches
that exception but returns without notifying its consumer, leaving the
wallpaper editor waiting for object processing to finish.

For a null capture result, continue through the existing result construction
and completion callback with an empty, nullable capture in GetObjectResult.
Skip the capture-only processing before entering the existing no-object
completion path. Keep the error log, successful capture processing and
cancellation checks intact. This does not enable native object extraction
or object-dependent wallpaper effects.

The patch is limited to beyond1lte. When updating the donor APK, check both
GetObjectResult's nullable result contract and the editor callback that
finishes loading; do not adapt obfuscated class names without tracing them.

After rebuilding, verify Gallery photo selection, lock-screen application,
reopening the editor, cancellation and built-in wallpapers on-device.
