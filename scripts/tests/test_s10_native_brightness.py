#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual kernel panel update and reproduce double-scaled HWC1 input."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest


class NativeBrightnessTests(unittest.TestCase):
    def test_actual_panel_update_keeps_hwc1_native_units(self):
        panel = (self.kernel / "drivers/video/fbdev/exynos/panel/panel_bl.c").read_text()
        start = panel.index("int panel_update_brightness(")
        end = panel.index("\nstatic int panel_bl_update_status", start)
        fixup = (self.kernel / "drivers/extremerom/fixups/brightness.c").read_text()
        fixup = fixup[fixup.index("static bool bootanim_set_brightness"):].replace("EXPORT_SYMBOL_GPL(get_fixed_brightness);", "")
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#define BOOTMODE_NORMAL 0
#define likely(x) (x)
#define get_extremerom_bootmode() BOOTMODE_NORMAL
#define PANEL_BL_SUBDEV_TYPE_DISP 0
#define PANEL_BL_SUBDEV_TYPE_AOD 1
#define PANEL_BL_SUBDEV_TYPE_HMD 2
#define CONFIG_SUPPORT_AOD_BL 1
#define mutex_lock(x) ((void)0)
#define mutex_unlock(x) ((void)0)
#define pr_alert(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
struct backlight_device { struct { int brightness; } props; };
struct panel_bl_device {
    int lock;
    struct backlight_device *bd;
    struct { int id; } props;
    struct { int brightness; } subdev[3];
};
struct panel_device { struct panel_bl_device panel_bl; int op_lock; };
static int programmed;
static bool is_valid_brightness(struct panel_bl_device *p, int brightness) {
    (void)p;
    return brightness >= 0 && brightness <= 48600;
}
static int panel_bl_set_brightness(struct panel_bl_device *p, int id, int force) {
    (void)id; (void)force;
    programmed = p->subdev[0].brightness;
    return 0;
}
'''
        main = r'''
int main(void) {
    struct backlight_device bd = { .props.brightness = 12800 };
    struct panel_device panel = { .panel_bl.bd = &bd };
    assert(panel_update_brightness(&panel) == 0);
    assert(programmed == 12800);
    bd.props.brightness = 1200;
#ifdef CONFIG_ONEUI7_WORKAROUND
    assert(panel_update_brightness(&panel) == -EINVAL);
    assert(programmed == 12800);
#else
    int inputs[] = { 0, 1, 100, 1200, 2400, 12800, 25500, 48600 };
    for (unsigned i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
        bd.props.brightness = inputs[i];
        assert(panel_update_brightness(&panel) == 0);
        assert(programmed == inputs[i]);
        assert(panel.panel_bl.subdev[1].brightness == inputs[i]);
    }
    bd.props.brightness = 48601;
    assert(panel_update_brightness(&panel) == -EINVAL);
#endif
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="s10-native-brightness-") as directory:
            root = Path(directory)
            source = root / "probe.c"
            source.write_text(fixture + "\n" + fixup + "\n" + panel[start:end] + "\n" + main)
            for mode, flags in (("old", ["-DCONFIG_ONEUI7_WORKAROUND"]), ("native", [])):
                executable = root / mode
                subprocess.run(["cc", "-std=gnu11", "-Werror", *flags, str(source), "-o", str(executable)], check=True)
                subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args, extra = parser.parse_known_args()
    NativeBrightnessTests.kernel = args.kernel
    unittest.main(argv=[__file__] + extra)
