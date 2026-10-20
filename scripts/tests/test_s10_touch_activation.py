#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the real input-core gate and the touchscreen HAL activation adapter."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def function(source, name):
    match = re.search(r"^(?:static )?(?:int|ssize_t) " + re.escape(name)
                      + r"\([\s\S]*?^\}", source, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing kernel implementation: {name}")
    return match.group()


class TouchActivationTests(unittest.TestCase):
    def test_real_hal_transitions_preserve_input_gate_and_handler_references(self):
        core = (self.kernel / "drivers/input/input.c").read_text()
        touchscreen = (self.kernel / "drivers/input/touchscreen/sec_ts/y771/sec_ts_fn.c").read_text()
        implementations = "\n".join(
            [function(core, name) for name in (
                "input_enable_device", "input_disable_device", "input_set_device_enabled")]
            + [function(touchscreen, name) for name in (
                "sec_ts_enabled_show", "sec_ts_enabled_store")])
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define PAGE_SIZE 4096
#define scnprintf snprintf
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
static int lock_error, opens, closes, open_error;
struct input_dev {
    int mutex, users, users_private;
    bool disabled;
    int (*open)(struct input_dev *);
    void (*close)(struct input_dev *);
};
struct sec_cmd_data { int unused; };
struct sec_ts_data { struct sec_cmd_data sec; struct input_dev *input_dev_touch; };
struct device { struct sec_cmd_data *data; };
struct device_attribute { int unused; };
static void *dev_get_drvdata(struct device *dev) { return dev->data; }
static int mutex_lock_interruptible(int *mutex) { (void)mutex; return lock_error; }
static void mutex_unlock(int *mutex) { (void)mutex; }
static int open_touch(struct input_dev *dev) { (void)dev; ++opens; return open_error; }
static void close_touch(struct input_dev *dev) { (void)dev; ++closes; }
'''
        proof = r'''
int main(void) {
    struct input_dev input = { .users = 3, .users_private = 3,
        .open = open_touch, .close = close_touch };
    struct sec_ts_data ts = { .input_dev_touch = &input };
    struct device dev = { .data = &ts.sec };
    char state[PAGE_SIZE];
#define WRITE(text) sec_ts_enabled_store(&dev, NULL, text, sizeof(text) - 1)

    /* Reproduce the old sleep gate, then resume through the real HAL ABI. */
    assert(input_set_device_enabled(&input, false) == 0);
    assert(input.disabled && input.users == 0 && input.users_private == 3);
    assert(closes == 1);
    assert(WRITE("2,0") == 3);
    assert(!input.disabled && input.users == 3 && opens == 1);
    assert(WRITE("2,1") == 3 && opens == 1);
    assert(WRITE("2,0") == 3 && opens == 1);
    assert(sec_ts_enabled_show(&dev, NULL, state) == 2 && !strcmp(state, "2\n"));

    /* OFF and both DOZE states close only after panel-off; repeats are safe. */
    for (int mode = 1; mode <= 4; ++mode) {
        char early[4], late[4];
        if (mode == 2) continue;
        snprintf(early, sizeof(early), "%d,0", mode);
        snprintf(late, sizeof(late), "%d,1", mode);
        int old_closes = closes;
        assert(sec_ts_enabled_store(&dev, NULL, early, 3) == 3);
        assert(!input.disabled && closes == old_closes);
        assert(sec_ts_enabled_store(&dev, NULL, late, 3) == 3);
        assert(input.disabled && input.users == 0 && closes == old_closes + 1);
        assert(input.users_private == 3);
        assert(sec_ts_enabled_store(&dev, NULL, late, 3) == 3);
        assert(closes == old_closes + 1);
        assert(sec_ts_enabled_show(&dev, NULL, state) == 2 && !strcmp(state, "1\n"));
        assert(WRITE("2,0") == 3 && !input.disabled && input.users == 3);
    }

    /* The actual HAL writes ten bytes, including NUL padding. */
    const char padded_off[10] = "1,1", padded_on[10] = "2,0";
    assert(sec_ts_enabled_store(&dev, NULL, padded_off, sizeof(padded_off)) == 10);
    assert(input.disabled);
    assert(sec_ts_enabled_store(&dev, NULL, padded_on, sizeof(padded_on)) == 10);
    assert(!input.disabled && input.users_private == 3);

    const char *invalid[] = { "", "1", "0,0", "5,0", "-1,1", "2,2", "2,-1", "2,0junk", "2,0,1" };
    int old_opens = opens, old_closes = closes;
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i)
        assert(sec_ts_enabled_store(&dev, NULL, invalid[i], strlen(invalid[i])) == -EINVAL);
    assert(opens == old_opens && closes == old_closes && !input.disabled);

    assert(WRITE("1,1") == 3 && input.disabled);
    open_error = -EIO;
    assert(WRITE("2,0") == -EIO);
    assert(input.disabled && input.users == 0 && input.users_private == 3);
    open_error = 0;
    lock_error = -EINTR;
    assert(WRITE("2,0") == -EINTR && input.disabled);
    lock_error = 0;
    assert(WRITE("2,0") == 3 && !input.disabled && input.users == 3);
    lock_error = -EINTR;
    assert(WRITE("1,1") == -EINTR && !input.disabled && input.users == 3);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="s10-touch-activation-") as directory:
            root = Path(directory)
            source = root / "probe.c"
            source.write_text(fixture + implementations + proof)
            executable = root / "probe"
            subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", "-fsanitize=undefined",
                            str(source), "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args, extra = parser.parse_known_args()
    TouchActivationTests.kernel = args.kernel
    unittest.main(argv=[__file__] + extra)
