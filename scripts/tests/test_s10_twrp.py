#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the recovery installer against temporary loop devices, never a phone."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s10_models import MODELS, layout_for, render_installer

ROOT = Path(__file__).resolve().parents[2]
ORDER = ('vbmeta', 'system', 'vendor', 'dtb', 'dtbo', 'boot')


def main(recovery=None, model='SM-G973F'):
    if os.geteuid() != 0:
        raise RuntimeError('Linux root is required for isolated temporary loop-device fixtures')
    template = render_installer(model)
    runner = ['sh']
    if recovery:
        recovery = recovery.resolve()
        runner = ['qemu-aarch64', '-L', str(recovery), str(recovery / 'sbin/busybox'), 'sh']
    subprocess.run(runner + ['-n', str(ROOT / 'target/beyond1lte/oneui9/installer/update-binary')], check=True)
    layout = layout_for(model)
    loops = []
    with tempfile.TemporaryDirectory(prefix='s10-twrp-test-') as temporary:
        root = Path(temporary)
        blocks, data, bin_path = root / 'blocks', root / 'data', root / 'bin'
        for directory in (blocks, data, bin_path):
            directory.mkdir()
        try:
            files, prefixes = {}, {}
            for index, name in enumerate(ORDER):
                image = root / (name + '.block')
                with image.open('wb') as stream:
                    stream.truncate(layout['partitions'][name]['bytes'])
                    stream.seek(0)
                    prefixes[name] = bytes([90 + index]) * 4096
                    stream.write(prefixes[name])
                loop = subprocess.check_output(['losetup', '--find', '--show', str(image)], text=True).strip()
                assert loop.startswith('/dev/loop')
                loops.append(loop)
                (blocks / name).symlink_to(loop)
                files[name] = image
            getprop = bin_path / 'getprop'
            getprop.write_text('''#!/bin/sh
case "$1" in
ro.twrp.version) echo 3.7.0_9-1 ;;
ro.product.device) echo "${FIXTURE_DEVICE:-beyond1lte}" ;;
ro.bootloader) echo "${FIXTURE_LOADER:-G973FXXSGHWC1}" ;;
ro.boot.vbmeta.device_state) echo unlocked ;;
ro.boot.flash.locked) echo 0 ;;
esac
''')
            getprop.chmod(0o755)
            if recovery:
                for tool in ('unzip', 'sha256sum', 'dd', 'head', 'readlink', 'awk', 'mktemp', 'sync', 'cat', 'rm'):
                    wrapper = bin_path / tool
                    wrapper.write_text(f'#!/bin/sh\nexec qemu-aarch64 -L "{recovery}" "{recovery}/sbin/busybox" {tool} "$@"\n')
                    wrapper.chmod(0o755)
            mounts = root / 'mounts'
            mounts.write_text(f'/dev/fixture-userdata {data} ext4 rw 0 0\n')
            script = root / 'update-binary'
            script.write_text(template.replace('BLOCK_ROOT=/dev/block/by-name', 'BLOCK_ROOT=' + str(blocks))
                              .replace('DATA=/data\n', 'DATA=' + str(data) + '\n')
                              .replace('MOUNTS=/proc/mounts', 'MOUNTS=' + str(mounts)))
            payloads = {name: bytes([10 + index]) * (8192 + index * 512) for index, name in enumerate(ORDER)}

            def package(case):
                path = root / (case + '.zip')
                partitions, chunks = [], []
                with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name in ORDER:
                        part = 'userdata' if case == 'forbidden-destination' and name == 'boot' else name
                        sectors = layout['partitions'][name]['bytes'] // 512
                        if case == 'wrong-capacity' and name == 'boot':
                            sectors += 1
                        entry = f'images/{part}/0000.part'
                        payload = payloads[name]
                        partitions.append(f'{part}\t{len(payload)}\t{sectors}\n')
                        chunks.append(f'{part}\t0\t{len(payload)}\t{hashlib.sha256(payload).hexdigest()}\t{entry}\n')
                        if case == 'missing-last-chunk' and name == 'boot':
                            continue
                        if case == 'corrupt-last-chunk' and name == 'boot':
                            payload = payload[:-1] + b'!'
                        archive.writestr(entry, payload)
                    archive.writestr('artisan/partitions.tsv', ''.join(partitions))
                    archive.writestr('artisan/chunks.tsv', ''.join(chunks))
                return path

            checks = []
            cases = ('wrong-device', 'wrong-bootloader', 'old-bootloader', 'dirty-data', 'wrong-capacity', 'mounted-target',
                     'forbidden-destination', 'corrupt-last-chunk', 'missing-last-chunk', 'valid')
            for case in cases:
                environment = dict(os.environ, PATH=str(bin_path) + ':' + os.environ['PATH'])
                environment['FIXTURE_DEVICE'] = MODELS[model]['device']
                environment['FIXTURE_LOADER'] = MODELS[model]['build']
                if case == 'wrong-device':
                    environment['FIXTURE_DEVICE'] = 'beyond1lte' if model != 'SM-G973F' else 'beyond2lte'
                if case == 'wrong-bootloader':
                    environment['FIXTURE_LOADER'] = 'G973USQU1ASD7'
                if case == 'old-bootloader':
                    environment['FIXTURE_LOADER'] = model.removeprefix('SM-') + 'XXU1ASD7'
                if case == 'dirty-data':
                    (data / 'system').mkdir()
                    (data / 'system/preserved').write_text('user data must survive rejection')
                if case == 'mounted-target':
                    mounts.write_text(f'/dev/fixture-userdata {data} ext4 rw 0 0\n{loops[2]} /vendor ext4 ro 0 0\n')
                result = subprocess.run(runner + [str(script), '3', '1', str(package(case))], env=environment,
                                        capture_output=True, text=True, timeout=90)
                if case == 'valid':
                    assert result.returncode == 0, result.stdout + result.stderr
                    assert 'block-device readback passed' in result.stdout
                    for name in ORDER:
                        with files[name].open('rb') as stream:
                            assert stream.read(len(payloads[name])) == payloads[name]
                else:
                    assert result.returncode != 0, case
                    for name in ORDER:
                        with files[name].open('rb') as stream:
                            assert stream.read(4096) == prefixes[name], f'preflight wrote {name}: {case}'
                checks.append(case)
                if case == 'dirty-data':
                    assert (data / 'system/preserved').read_text() == 'user data must survive rejection'
                    shutil.rmtree(data / 'system')
                if case == 'mounted-target':
                    mounts.write_text(f'/dev/fixture-userdata {data} ext4 rw 0 0\n')
            print('PASS: ' + ', '.join(checks) + '; rejected cases wrote no blocks; clean installation readback matched')
        finally:
            for loop in reversed(loops):
                subprocess.run(['losetup', '-d', loop], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery-root', type=Path, help='Execute the real ARM64 recovery shell/applets under QEMU')
    parser.add_argument('--model', choices=MODELS, default='SM-G973F')
    args = parser.parse_args()
    main(args.recovery_root, args.model)
