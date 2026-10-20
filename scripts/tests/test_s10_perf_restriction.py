#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual S10 perf restriction default, predicate and syscall guard."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    core = (args.kernel / "kernel/events/core.c").read_text()
    header = (args.kernel / "include/linux/perf_event.h").read_text()
    defaults = re.search(r"#ifdef CONFIG_SECURITY_PERF_EVENTS_RESTRICT\n.*?\n#endif", core, re.S)
    predicate = re.search(r"static inline bool perf_paranoid_any\(void\)\n\{.*?\n\}", header, re.S)
    syscall = core[core.index("SYSCALL_DEFINE5(perf_event_open,"):]
    guard = re.search(r"\tif \(perf_paranoid_any\(\).*?\n\t\treturn .*?;", syscall)
    if not defaults or not predicate or not guard or guard.start() > syscall.index("security_perf_event_open"):
        raise RuntimeError("Actual perf restriction default, predicate or early syscall guard is missing")
    if "CONFIG_SECURITY_PERF_EVENTS_RESTRICT=y" not in (args.kernel / "arch/arm64/configs/beyond1lte.config").read_text().splitlines():
        raise RuntimeError("The S10 board configuration must enable the functional restriction")
    fixture = """
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#define __read_mostly
#define CAP_SYS_ADMIN 21
static bool has_admin;
static bool capable(int capability) { assert(capability == CAP_SYS_ADMIN); return has_admin; }
""" + defaults.group() + "\n" + predicate.group() + "\nstatic int check_open(void) {\n" + guard.group() + "\nreturn 0;\n}\n" + """
int main(void) {
#ifdef CONFIG_SECURITY_PERF_EVENTS_RESTRICT
    assert(sysctl_perf_event_paranoid == 3);
#else
    assert(sysctl_perf_event_paranoid == 2);
#endif
    has_admin = false;
    for (int value = -1; value <= 2; ++value) {
        sysctl_perf_event_paranoid = value;
        assert(check_open() == 0);
    }
    sysctl_perf_event_paranoid = 3;
    assert(check_open() == -EACCES);
    sysctl_perf_event_paranoid = 4;
    assert(check_open() == -EACCES);
    has_admin = true;
    assert(check_open() == 0);
    return 0;
}
"""
    with tempfile.TemporaryDirectory(prefix="s10-perf-restrict-") as temporary:
        source = Path(temporary) / "fixture.c"
        source.write_text(fixture)
        for enabled in (False, True):
            binary = Path(temporary) / ("enabled" if enabled else "disabled")
            flags = ["-DCONFIG_SECURITY_PERF_EVENTS_RESTRICT=1"] if enabled else []
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", *flags, str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
    print("Passed actual perf defaults and unprivileged/admin guard checks; device enforcement remains untested.")


if __name__ == "__main__":
    main()
