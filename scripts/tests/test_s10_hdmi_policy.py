#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify HDMI route restoration against the pinned donor and HWC1 inputs."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.s10_hdmi_audio import configure, policy_patched, ORIGINAL_SHA256, PATCHED_SHA256, OFFSET


def topology(node):
    return node.tag, sorted(node.attrib.items()), (node.text or '').strip(), [topology(child) for child in node]


def main(system, vendor):
    relative = Path('vendor_overlay/31/etc/audio_policy_configuration_sec.xml')
    original = (system / relative).read_bytes()
    before, after = ET.fromstring(original), ET.fromstring(policy_patched(original))
    primary = after.find("./modules/module[@name='primary']")
    hdmi = primary.find("./mixPorts/mixPort[@name='hdmi']")
    route = primary.find("./routes/route[@sink='Aux Device Out']")
    assert hdmi.attrib == {'flags': 'AUDIO_OUTPUT_FLAG_MULTI_CH', 'name': 'hdmi', 'role': 'source'}
    assert hdmi.find('profile').attrib == {
        'channelMasks': 'AUDIO_CHANNEL_OUT_STEREO AUDIO_CHANNEL_OUT_5POINT1',
        'format': 'AUDIO_FORMAT_PCM_16_BIT', 'name': '', 'samplingRates': '48000'}
    assert route.attrib == {'sink': 'Aux Device Out', 'sources': 'hdmi', 'type': 'mix'}
    assert primary.find("./devicePorts/devicePort[@tagName='Aux Device Out']").get('type') == 'AUDIO_DEVICE_OUT_AUX_DIGITAL'
    assert 'Aux Device Out' not in [node.text for node in primary.findall('./attachedDevices/item')]
    primary.find('mixPorts').remove(hdmi)
    primary.find('routes').remove(route)
    assert topology(before) == topology(after), 'unrelated policy topology changed'
    with tempfile.TemporaryDirectory(prefix='s10-hdmi-policy-') as temporary:
        root = Path(temporary)
        work_system, work_vendor = root / 'system', root / 'vendor'
        inputs = [(system / layer / str(api) / 'etc/audio_policy_configuration_sec.xml',
                   work_system / layer / str(api) / 'etc/audio_policy_configuration_sec.xml')
                  for layer in ('vendor_overlay', 'product/vendor_overlay') for api in range(28, 35)]
        inputs += [(system / 'lib64/libaudiopolicycomponents.so', work_system / 'lib64/libaudiopolicycomponents.so'),
                   (vendor / 'lib/hw/audio.primary.exynos9820.so', work_vendor / 'lib/hw/audio.primary.exynos9820.so')]
        for source, destination in inputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            os.setxattr(destination, 'user.hdmi_test', b'preserved')
        def snapshot():
            return {path: (path.read_bytes(), path.stat().st_ino, path.stat().st_mode,
                           path.stat().st_uid, path.stat().st_gid,
                           {key: os.getxattr(path, key) for key in os.listxattr(path)}) for _, path in inputs}
        # A bad overlay must be rejected before even the first valid overlay changes.
        bad = inputs[13][1]
        bad.write_bytes(bad.read_bytes() + b'\n')
        rejected = snapshot()
        try:
            configure(work_system, work_vendor)
        except ValueError:
            pass
        else:
            raise AssertionError('unknown overlay accepted')
        assert snapshot() == rejected
        bad.write_bytes(inputs[13][0].read_bytes())
        # A valid framework and policy must not admit a mismatched HAL.
        hal = inputs[-1][1]
        source_hal = hal.read_bytes()
        assert hashlib.sha256(source_hal).hexdigest() == ORIGINAL_SHA256
        hal.write_bytes(source_hal[:-1])
        rejected = snapshot()
        try:
            configure(work_system, work_vendor)
        except ValueError:
            pass
        else:
            raise AssertionError('unknown HAL accepted')
        assert snapshot() == rejected
        hal.write_bytes(source_hal)
        saved = snapshot()
        record = configure(work_system, work_vendor)
        assert len(record['policy_files']) == 14 and record['multi_ch_flag'] == 0x2000000
        result = snapshot()
        for path, current in result.items():
            assert current[1:] == saved[path][1:], f'Android metadata changed: {path.name}'
        for _, path in inputs[:14]:
            assert path.read_bytes() == policy_patched(saved[path][0])
        assert result[inputs[-2][1]] == saved[inputs[-2][1]], 'framework modified'
        assert hashlib.sha256(hal.read_bytes()).hexdigest() == PATCHED_SHA256
        assert [i for i, pair in enumerate(zip(source_hal, hal.read_bytes())) if pair[0] != pair[1]] == [OFFSET + 2]
    print('PASS: HDMI route, unchanged unrelated topology, both overlay layers, input rejection and Android metadata')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--vendor', type=Path, required=True)
    args = parser.parse_args()
    main(args.system, args.vendor)
