#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconstruct a Beta payload from GitHub download parts; verify every SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

MODELS = ('SM-G970F', 'SM-G973F', 'SM-G975F')


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_file(directory, spec, name):
    if (spec.get('name') != name or type(spec.get('bytes')) is not int or spec['bytes'] <= 0
            or not re.fullmatch('[0-9a-f]{64}', spec.get('sha256', ''))):
        raise ValueError('Invalid download record: ' + name)
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size != spec['bytes']:
        raise ValueError('Missing file or incorrect size: ' + name)
    return path


def join_release(directory, model):
    if model not in MODELS:
        raise ValueError('Unsupported model')
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'DOWNLOADS.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('version') != 'v35-beta':
        raise ValueError('The matching V35 Beta DOWNLOADS.json is required')
    record = manifest['models'][model]
    payload, installer = record['payload'], record['installer']
    name = f'YuROM_Ultra_OneUI9_v35_BETA_{model}_TWRP.zip'
    if (payload.get('name') != name or type(payload.get('bytes')) is not int or payload['bytes'] <= 0
            or not re.fullmatch('[0-9a-f]{64}', payload.get('sha256', ''))):
        raise ValueError('Invalid payload record')
    target = directory / name
    small = checked_file(directory, installer, name.replace('_TWRP.zip', '_INSTALLER_r4.zip'))
    if file_sha(small) != installer['sha256']:
        raise ValueError('The installer checksum is incorrect')
    if target.exists() or target.is_symlink():
        if not target.is_symlink() and target.is_file() and file_sha(target) == payload['sha256']:
            return target
        raise FileExistsError('Refusing to replace an existing file: ' + name)
    parts = payload['parts']
    if (not isinstance(parts, list) or not 1 <= len(parts) <= 8
            or sum(part.get('bytes', 0) for part in parts) != payload['bytes']):
        raise ValueError('Invalid download part list')
    paths = [checked_file(directory, part, name + f'.{index:03d}')
             for index, part in enumerate(parts, 1)]
    if shutil.disk_usage(directory).free < payload['bytes'] + 128 * 1024**2:
        raise OSError('Insufficient free space for the reconstructed ZIP')
    temporary = target.with_name(target.name + '.partial')
    opened = False
    total = hashlib.sha256()
    try:
        with temporary.open('xb') as output:
            opened = True
            for path, part in zip(paths, parts):
                checksum = hashlib.sha256()
                with path.open('rb') as source:
                    while block := source.read(1024**2):
                        checksum.update(block)
                        total.update(block)
                        output.write(block)
                if checksum.hexdigest() != part['sha256']:
                    raise ValueError('Corrupt download part: ' + path.name)
        if temporary.stat().st_size != payload['bytes'] or total.hexdigest() != payload['sha256']:
            raise ValueError('The reconstructed payload checksum is incorrect')
        # Publishing a hardlink atomically refuses an existing name on Windows and Linux.
        target.hardlink_to(temporary)
        return target
    finally:
        if opened and temporary.exists():
            temporary.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', choices=MODELS)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    result = join_release(args.directory, args.model)
    print(f'PASS: {result.name} and its matching installer verified. Keep both ZIPs together.')
