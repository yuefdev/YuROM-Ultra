#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a full-image, model-checked original-layout S10 TWRP ZIP without flashing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import zipfile
from s10_models import MODELS, layout_for, render_installer

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1024 ** 3
ORDER = ('vbmeta', 'system', 'vendor', 'dtb', 'dtbo', 'boot')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pack_image(archive, name, stream):
    chunks = []
    position = stream.tell()
    end = stream.seek(0, os.SEEK_END)
    stream.seek(position)
    while first := stream.read(min(CHUNK, 1024**2)):
        index = len(chunks)
        entry = f'images/{name}/{index:04d}.part'
        checksum = hashlib.sha256()
        count = 0
        info = zipfile.ZipInfo(entry)
        info.file_size = min(CHUNK, len(first) + end - stream.tell())
        info.compress_type = archive.compression
        info._compresslevel = archive.compresslevel
        # Recovery BusyBox needs classic entry headers even when the directory is ZIP64.
        with archive.open(info, 'w', force_zip64=False) as output:
            block = first
            while block:
                output.write(block)
                checksum.update(block)
                count += len(block)
                if count == CHUNK:
                    break
                block = stream.read(min(CHUNK-count, 1024**2))
        chunks.append(f'{name}\t{index * CHUNK // 1024**2}\t{count}\t{checksum.hexdigest()}\t{entry}\n')
    return chunks


def build(candidate, kernel, boot, avb, output, version, records):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,47}', version):
        raise ValueError('Invalid ROM version')
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Use a new ZIP in an existing output directory')
    if not records.is_dir() or records.resolve().is_relative_to(ROOT):
        raise ValueError('Use an existing external records directory')
    source = json.loads((candidate / 'input.json').read_text())
    model = source.get('model')
    if model not in MODELS:
        raise ValueError('An explicitly registered Exynos S10 model is required')
    profile = MODELS[model]
    layout = layout_for(model)
    packed = json.loads((candidate / 'images.json').read_text())
    kernels = json.loads((kernel / 'input.json').read_text())
    bootstrap = json.loads((avb / 'input.json').read_text())
    if (source.get('donor_build') != 'S942BXXU4ZZH6'
            or source.get('stock_build') != profile['build'] or source.get('repartition') is not False
            or source.get('local_adb_enrolment') or (candidate / 'tree/adb_keys').exists()
            or (candidate / 'tree/system/etc/security/adb_keys').exists()):
        raise ValueError('Expected a sanitised, original-layout candidate with matching model stock firmware')
    if model != 'SM-G973F' and (kernels.get('model') != model or source.get('kernel', {}).get('model') != model or packed.get('model') != model):
        raise ValueError('Kernel, images and candidate must belong to the same model')
    if (source.get('artisan_control', {}).get('surface') != 'native-settings-fragment'
            or not source.get('s10_hdmi_audio_compatibility')
            or not source.get('s10_native_zygote_compatibility')
            or not source.get('s10_legacy_scheduler_compatibility')
            or not source.get('s10_boot_performance')):
        raise ValueError('The current native Settings, CE, HDMI and scheduler integrations are required')
    bundle = source['artisan_control']
    if source.get('ce_vold_sha256') != '1856ffbd5dfd3922c0987fced54031e40ebad03bc84c6b0f540995946dbc7009':
        raise ValueError('The tokenless-CE donor dependency is required')
    if (bootstrap.get('model') != model or bootstrap.get('flags') != 3
            or bootstrap.get('algorithm') != 'NONE' or not bootstrap.get('stock_descriptors_retained')):
        raise ValueError('The verified model-specific disabled-AVB metadata is required')
    if digest(boot) != source['s10_boot_performance']['kernel_sha256']:
        raise ValueError('Boot image does not match the maintained performance profile')
    images = {'system': candidate / 'system.img', 'vendor': candidate / 'vendor.img',
              'boot': boot, 'dtb': kernel / 'dtb.img', 'dtbo': kernel / 'dtbo.img', 'vbmeta': avb / 'vbmeta.img'}
    inventory = {}
    magic = {'system': (1024, b'\xe2\xe1\xf5\xe0'), 'vendor': (1080, b'\x53\xef'),
             'boot': (0, b'ANDROID!'), 'dtb': (0, b'\xd7\xb7\xab\x1e'),
             'dtbo': (0, b'\xd7\xb7\xab\x1e'), 'vbmeta': (0, b'AVB0')}
    for name, path in images.items():
        expected = (packed['images'][name + '.img'] if name in ('system', 'vendor')
                    else bootstrap['images']['vbmeta.img'] if name == 'vbmeta'
                    else kernels['images'][name + '.img'] if name in ('dtb', 'dtbo')
                    else {'size': layout['partitions']['boot']['bytes'], 'sha256': source['s10_boot_performance']['kernel_sha256']})
        size = path.stat().st_size
        checksum = digest(path)
        if size != expected['size'] or checksum != expected['sha256'] or size > layout['partitions'][name]['bytes']:
            raise ValueError('Image size or checksum mismatch: ' + name)
        offset, signature = magic[name]
        with path.open('rb') as stream:
            stream.seek(offset)
            if stream.read(len(signature)) != signature:
                raise ValueError('Unexpected image format: ' + name)
        inventory[name] = {'bytes': size, 'sha256': checksum,
                           'partition_sectors': layout['partitions'][name]['bytes'] // 512}
    vbmeta = images['vbmeta'].read_bytes()
    if struct.unpack_from('>I', vbmeta, 120)[0] != 3:
        raise ValueError('AVB disable flags are absent')
    chunks, partitions = [], []
    for name in ORDER:
        spec = inventory[name]
        partitions.append(f"{name}\t{spec['bytes']}\t{spec['partition_sectors']}\n")
    manifest = {'schema': 1, 'rom': 'YuROM Ultra', 'version': version, 'model': model,
                'recovery_devices': [profile['device'].removesuffix('lte'), profile['device']], 'donor_build': source['donor_build'],
                'stock_vendor_build': source['stock_build'], 'clean_install_required': True,
                'automatic_data_format': False, 'repartition': False, 'images': inventory,
                'artisan_outputs': bundle['outputs'], 'zip_install_on_device_verified': False,
                'selinux_enforcing_validated': False, 'physical_model_acceptance': 'pending',
                'adaptive_performance_control': source.get('adaptive_performance_control', {})}
    temporary = output.with_name(output.name + '.partial')
    if temporary.exists():
        raise ValueError('A previous partial ZIP must be investigated first')
    with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        info = zipfile.ZipInfo('META-INF/com/google/android/update-binary', (2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100755 << 16
        archive.writestr(info, render_installer(model).encode())
        archive.writestr('META-INF/com/google/android/updater-script', '# Installation is implemented by update-binary.\n')
        for name in ORDER:
            with images[name].open('rb') as stream:
                chunks.extend(pack_image(archive, name, stream))
        archive.writestr('artisan/partitions.tsv', ''.join(partitions))
        archive.writestr('artisan/chunks.tsv', ''.join(chunks))
        archive.writestr('artisan/manifest.json', json.dumps(manifest, indent=2) + '\n')
        instructions = (ROOT / 'target/beyond1lte/oneui9/installer/INSTALL.md').read_text()
        if model != 'SM-G973F':
            instructions = instructions.replace('G973F', model.removeprefix('SM-')).replace('beyond1lte', profile['device']).replace('beyond1', profile['device'].removesuffix('lte')).replace('HWC1', 'HWC2')
        archive.writestr('INSTALL.md', instructions.encode())
    # Read and hash the entire archive, not merely its central directory/CRC.
    with zipfile.ZipFile(temporary) as archive:
        for line in chunks:
            name, offset, size, expected, entry = line.split()
            with archive.open(entry) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise RuntimeError('Packed payload checksum mismatch: ' + entry)
        assert len(archive.namelist()) == len(set(archive.namelist()))
    os.rename(temporary, output)
    checksum = digest(output)
    output.with_suffix(output.suffix + '.sha256').write_text(checksum + '  ' + output.name + '\n')
    report = dict(manifest, zip_file=output.name, zip_bytes=output.stat().st_size, zip_sha256=checksum,
                  packed_image_chunks_verified=len(chunks))
    (records / 'package.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'zip': str(output), 'bytes': output.stat().st_size, 'sha256': checksum,
                      'model': model, 'chunks_verified': len(chunks)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('candidate', 'kernel', 'boot', 'avb', 'output', 'records'):
        parser.add_argument('--' + argument, type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    build(args.candidate, args.kernel, args.boot, args.avb, args.output, args.version, args.records)
