#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a probe that loads MediaOutput from the installed Settings APK."""
import argparse
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_artisan_control import ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build-tools', 'android-jar', 'output', 'records'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir() or not args.records.is_dir() or args.records.resolve().is_relative_to(ROOT):
        parser.error('Use a new JAR and an existing external records directory')
    source = Path(__file__).parent / 'android/artisan-settings/MediaOutputProbe.java'
    implementation = ROOT / 'packages/ArtisanControl/src/com/android/settings/artisan/MediaOutput.java'
    with tempfile.TemporaryDirectory(prefix='media-output-probe-') as temporary, (args.records / 'media-probe-build.log').open('w') as log:
        root = Path(temporary); classes = root / 'classes'; dex = root / 'dex'; classes.mkdir(); dex.mkdir()
        run(['javac', '--release', '11', '-classpath', args.android_jar, '-d', classes, implementation, source], log)
        # Compile-time implementation classes are deliberately excluded: the
        # device must execute the version shipped in the live Settings APK.
        selected = sorted((classes / 'com/artisanrom/tests').rglob('*.class'))
        run(['java', '-cp', args.build_tools / 'lib/d8.jar', 'com.android.tools.r8.D8', '--min-api', '31',
             '--lib', args.android_jar, '--classpath', classes, '--output', dex, *selected], log)
        with zipfile.ZipFile(args.output, 'w') as archive:
            archive.write(dex / 'classes.dex', 'classes.dex', compress_type=zipfile.ZIP_STORED)
    print('Media output probe built; production implementation is loaded from Settings at runtime')


if __name__ == '__main__':
    main()
