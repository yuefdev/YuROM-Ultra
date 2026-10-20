#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise Beta assembly and bounded download reconstruction using temporary files."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assemble_s10_public_test as release
import build_s10_twrp as twrp
try:
    from join_yurom_beta import join_release
except ImportError:
    join_release = None

MODELS = ('SM-G970F', 'SM-G973F', 'SM-G975F')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='yurom-release-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = release.ROOT
        release.ROOT = self.root / 'source'
        self.addCleanup(setattr, release, 'ROOT', self.original)
        self.records = self.root / 'records'
        self.records.mkdir()
        (release.ROOT / 'out').mkdir(parents=True)
        display = release.ROOT / 'target/beyond1lte/oneui9/display'
        display.mkdir(parents=True)
        (display / 'profiles.json').write_text(json.dumps({'models': {model: {} for model in MODELS}}))
        installer = display.parent / 'installer'
        installer.mkdir()
        (installer / 'RELEASE_TR.md').write_text('YuROM Ultra {{VERSION}}\n')

    def fixture(self, version):
        tag = version.removesuffix('-test')
        for model in MODELS:
            records = self.records / model / tag
            records.mkdir(parents=True)
            items = []
            for suffix in ('TWRP', 'INSTALLER_r4'):
                name = f'YuROM_Ultra_{version}_{model}_{suffix}.zip'
                data = (model + suffix).encode()
                path = release.ROOT / 'out' / name
                path.write_bytes(data)
                path.with_suffix('.zip.sha256').write_text(sha(data) + '  ' + name + '\n')
                items.append((name, len(data), sha(data)))
            common = {'model': model, 'version': version}
            (records / 'package.json').write_text(json.dumps(dict(common, rom='YuROM Ultra',
                packed_image_chunks_verified=11, clean_install_required=True, repartition=False,
                zip_file=items[0][0], zip_bytes=items[0][1], zip_sha256=items[0][2])))
            (records / 'bootstrap-package.json').write_text(json.dumps(dict(common,
                payload_sha256=items[0][2], legacy_ufs_alias_supported=True, recovery_shell='busybox-sh',
                original_installer_checks_preserved=True, launcher_file=items[1][0],
                launcher_bytes=items[1][1], launcher_sha256=items[1][2])))
        acceptance = self.records / 'acceptance.json'
        acceptance.write_text(json.dumps({'version': version, 'model': 'SM-G973F'}))
        return acceptance

    def test_beta_assembles_six_exact_files_with_beta_channel(self):
        acceptance = self.fixture('v35-beta')
        output = release.ROOT / 'out/release'
        release.assemble('v35-beta', output, self.records, acceptance)
        report = json.loads((output / 'RELEASE.json').read_text())
        self.assertEqual(report['channel'], 'beta')
        self.assertEqual(len(list(output.glob('*/*.zip'))), 6)
        self.assertIn('v35-beta', (output / 'KURULUM_TR.md').read_text())

    def test_legacy_test_release_remains_supported(self):
        acceptance = self.fixture('v34-test')
        output = release.ROOT / 'out/release'
        release.assemble('v34-test', output, self.records, acceptance)
        self.assertEqual(json.loads((output / 'RELEASE.json').read_text())['channel'], 'public-test')

    def test_same_size_corrupt_payload_is_rejected_before_linking(self):
        acceptance = self.fixture('v35-test')
        payload = next((release.ROOT / 'out').glob('*_TWRP.zip'))
        data = payload.read_bytes()
        payload.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        with self.assertRaises(AssertionError):
            release.assemble('v35-test', release.ROOT / 'out/release', self.records, acceptance)
        self.assertFalse((release.ROOT / 'out/release').exists())

    def download_fixture(self):
        self.assertIsNotNone(join_release, 'The Beta reconstruction helper is missing')
        name = 'YuROM_Ultra_OneUI9_v35_BETA_SM-G973F_TWRP.zip'
        data = b'PK-reconstructed-payload' * 1000
        parts = []
        for index, content in enumerate((data[:7001], data[7001:]), 1):
            part = name + f'.{index:03d}'
            (self.root / part).write_bytes(content)
            parts.append({'name': part, 'bytes': len(content), 'sha256': sha(content)})
        installer = name.replace('_TWRP.zip', '_INSTALLER_r4.zip')
        (self.root / installer).write_bytes(b'launcher')
        record = {'payload': {'name': name, 'bytes': len(data), 'sha256': sha(data), 'parts': parts},
                  'installer': {'name': installer, 'bytes': 8, 'sha256': sha(b'launcher')}}
        (self.root / 'DOWNLOADS.json').write_text(json.dumps({'schema': 1, 'version': 'v35-beta',
                                                           'models': {'SM-G973F': record}}))
        return name, data, parts

    def test_download_parts_reconstruct_exact_zip_and_preserve_parts(self):
        name, data, parts = self.download_fixture()
        join_release(self.root, 'SM-G973F')
        self.assertEqual((self.root / name).read_bytes(), data)
        self.assertTrue(all((self.root / row['name']).exists() for row in parts))

    def test_bad_download_part_leaves_no_complete_or_partial_zip(self):
        name, data, parts = self.download_fixture()
        (self.root / parts[-1]['name']).write_bytes(b'!' * parts[-1]['bytes'])
        with self.assertRaises(ValueError):
            join_release(self.root, 'SM-G973F')
        self.assertFalse((self.root / name).exists())
        self.assertFalse((self.root / (name + '.partial')).exists())

    def test_reconstruction_does_not_overwrite_an_existing_file(self):
        name, data, parts = self.download_fixture()
        (self.root / name).write_bytes(b'preserve this file')
        with self.assertRaises(FileExistsError):
            join_release(self.root, 'SM-G973F')
        self.assertEqual((self.root / name).read_bytes(), b'preserve this file')

    def test_existing_valid_payload_still_requires_a_valid_installer(self):
        name, data, parts = self.download_fixture()
        (self.root / name).write_bytes(data)
        installer = self.root / name.replace('_TWRP.zip', '_INSTALLER_r4.zip')
        installer.write_bytes(b'bad-file')
        with self.assertRaises(ValueError):
            join_release(self.root, 'SM-G973F')

    def test_file_created_at_publication_time_is_preserved(self):
        name, data, parts = self.download_fixture()
        target = self.root / name
        original_rename = Path.rename
        original_hardlink = Path.hardlink_to
        def racing_rename(source, destination):
            target.write_bytes(b'concurrent file')
            return original_rename(source, destination)
        def racing_hardlink(destination, source):
            target.write_bytes(b'concurrent file')
            return original_hardlink(destination, source)
        with patch.object(Path, 'rename', racing_rename), patch.object(Path, 'hardlink_to', racing_hardlink):
            with self.assertRaises(FileExistsError):
                join_release(self.root, 'SM-G973F')
        self.assertEqual(target.read_bytes(), b'concurrent file')

    def test_image_chunk_packing_streams_and_preserves_offsets_and_hashes(self):
        self.assertTrue(hasattr(twrp, 'pack_image'), 'Bounded image chunk packing is missing')
        original = twrp.CHUNK
        twrp.CHUNK = 1024**2
        self.addCleanup(setattr, twrp, 'CHUNK', original)
        content = b'A' * (2 * twrp.CHUNK) + b'final-block'
        class BoundedStream(io.BytesIO):
            def read(self, count=-1):
                if not 0 < count <= 1024**2:
                    raise AssertionError('An unbounded read was attempted')
                return super().read(count)
        path = self.root / 'chunks.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            chunks = twrp.pack_image(archive, 'system', BoundedStream(content))
        self.assertEqual(len(chunks), 3)
        with zipfile.ZipFile(path) as archive:
            decoded = b''
            for index, line in enumerate(chunks):
                name, offset, size, checksum, entry = line.split()
                block = archive.read(entry)
                self.assertEqual(name, 'system')
                self.assertEqual(int(offset), index * twrp.CHUNK // 1024**2)
                self.assertEqual(int(size), len(block))
                self.assertEqual(checksum, sha(block))
                decoded += block
        self.assertEqual(decoded, content)


if __name__ == '__main__':
    unittest.main()
