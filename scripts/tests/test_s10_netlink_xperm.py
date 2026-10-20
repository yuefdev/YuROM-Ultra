#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the actual kernel xperm aggregation functions against NLMSG/IOCTL cases."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r"^void " + name + r"\([^;]+?\n\{", source, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Kernel function is missing: {name}")
    start = match.end() - 1
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    source = (args.kernel / "security/selinux/ss/services.c").read_text()
    avtab = (args.kernel / "security/selinux/ss/avtab.h").read_text()
    security = (args.kernel / "security/selinux/include/security.h").read_text()
    constants = "\n".join(re.findall(r"^#define (?:AVTAB_XPERMS_\w+|XPERMS_\w+)\s+(?:0x[0-9a-fA-F]+|[0-9]+).*$", avtab + "\n" + security, re.MULTILINE))
    fixture = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define BUG() abort()
#define security_xperm_set(p, bit) ((p)[(bit) / 32] |= 1U << ((bit) % 32))
#define security_xperm_test(p, bit) (!!((p)[(bit) / 32] & (1U << ((bit) % 32))))
struct extended_perms_data { u32 p[8]; };
struct extended_perms { struct extended_perms_data drivers; unsigned int len; };
struct extended_perms_decision {
    u8 driver, used;
    struct extended_perms_data *allowed, *auditallow, *dontaudit;
};
struct avtab_extended_perms { u8 specified, driver; struct extended_perms_data perms; };
struct avtab_node {
    struct { unsigned int specified; } key;
    struct { union { struct avtab_extended_perms *xperms; } u; } datum;
};
'''
    cases = r'''
int main(void) {
    struct avtab_extended_perms rule = { .specified = AVTAB_XPERMS_NLMSG, .driver = 3 };
    struct avtab_node node = { .key.specified = AVTAB_XPERMS_ALLOWED, .datum.u.xperms = &rule };
    struct extended_perms drivers = {0};
    struct extended_perms_data allowed = {0}, audit = {0}, denied = {0};
    struct extended_perms_decision decision = { .driver = 3, .allowed = &allowed, .auditallow = &audit, .dontaudit = &denied };
    security_xperm_set(rule.perms.p, 0xe9); /* AUDIT_GET is 0x3e9. */
    services_compute_xperms_drivers(&drivers, &node);
    assert(drivers.len == 1 && security_xperm_test(drivers.drivers.p, 3));
    assert(!security_xperm_test(drivers.drivers.p, 0));
    services_compute_xperms_decision(&decision, &node);
    assert(security_xperm_test(allowed.p, 0xe9));
    assert(!security_xperm_test(allowed.p, 0xea));
    memset(&allowed, 0, sizeof(allowed));
    decision.driver = 0; decision.used = 0;
    services_compute_xperms_decision(&decision, &node);
    assert(!decision.used && !security_xperm_test(allowed.p, 0xe9));
    decision.driver = 3;
    node.key.specified = AVTAB_XPERMS_AUDITALLOW;
    services_compute_xperms_decision(&decision, &node);
    assert(security_xperm_test(audit.p, 0xe9) && !security_xperm_test(audit.p, 0xea));
    node.key.specified = AVTAB_XPERMS_DONTAUDIT;
    services_compute_xperms_decision(&decision, &node);
    assert(security_xperm_test(denied.p, 0xe9) && !security_xperm_test(denied.p, 0xea));
    rule.specified = AVTAB_XPERMS_IOCTLFUNCTION; rule.driver = 0x54;
    decision.driver = 0x54; node.key.specified = AVTAB_XPERMS_ALLOWED;
    memset(&allowed, 0, sizeof(allowed));
    services_compute_xperms_decision(&decision, &node);
    assert(security_xperm_test(allowed.p, 0xe9) && !security_xperm_test(allowed.p, 0xea));
    rule.specified = AVTAB_XPERMS_IOCTLDRIVER;
    memset(&rule.perms, 0, sizeof(rule.perms));
    security_xperm_set(rule.perms.p, 0x54);
    services_compute_xperms_decision(&decision, &node);
    for (unsigned int i = 0; i < 256; i++) assert(security_xperm_test(allowed.p, i));
    return 0;
}
'''
    body = fixture + "\n" + constants + "\n" + function(source, "services_compute_xperms_drivers") + "\n" + function(source, "services_compute_xperms_decision") + "\n" + cases
    with tempfile.TemporaryDirectory(prefix="s10-xperm-") as temporary:
        root = Path(temporary)
        test = root / "check.c"
        test.write_text(body)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(test), "-o", str(root / "check")], check=True)
        subprocess.run([str(root / "check")], check=True)
    print("PASS: real kernel NLMSG driver filtering, permission scope, audit rules and legacy IOCTL aggregation")


if __name__ == "__main__":
    main()
