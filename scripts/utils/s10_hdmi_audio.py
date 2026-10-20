#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore the S10 HDMI policy route and match its HAL to MULTI_CH bit 25.

HWC1 tests bit 24 before selecting the HDMI stream. GZD7 and the pinned S26
donor pass bit 25, which otherwise falls through to the unsupported-output
branch. The HAL edit changes one pinned instruction. The policy restores the
stock 48 kHz stereo/5.1 stream without making HDMI permanently attached.
Device playback must still be tested after rebuilding.
"""
import hashlib
from pathlib import Path
import sys

ORIGINAL_SHA256 = '7866ba84edbbf9ed6120924a2fc1bdb434725efc56bb872f4ace896d71657cbd'
PATCHED_SHA256 = '15e023959e4eb24cb248d6d63075b8807a6d4c216f008d87f50bbe6a9c9fadea'
OFFSET = 0xd78a  # VA 0xe78a: lsls.w r0,r10,#7 -> #6; following BMI is unchanged.
BEFORE = bytes.fromhex('5feaca10')
AFTER = bytes.fromhex('5fea8a10')
POLICY_SHA256 = 'c70c4b9a5cef261e3df1e2680f15ba106baf198196f0ac22162253016c7dbdfe'
COMPONENTS_SHA256 = '1b1d7f1e73b296d3c815cd4f2ff02fce9c95fa8a067e1ff9282336c817dae6cb'


def policy_patched(data):
    """Add only the missing stream and route to the donor's declared HDMI sink."""
    if hashlib.sha256(data).hexdigest() != POLICY_SHA256:
        raise ValueError('unregistered donor audio policy; refusing HDMI route patch')
    mix_anchor = b'                <mixPort name="primary-in" role="sink">\n'
    route_anchor = b'                <route sink="primary-in" '
    if data.count(mix_anchor) != 1 or data.count(route_anchor) != 1:
        raise ValueError('unexpected donor primary audio topology')
    mix = (b'                <mixPort flags="AUDIO_OUTPUT_FLAG_MULTI_CH" name="hdmi" role="source">\n'
           b'                    <profile channelMasks="AUDIO_CHANNEL_OUT_STEREO AUDIO_CHANNEL_OUT_5POINT1" '
           b'format="AUDIO_FORMAT_PCM_16_BIT" name="" samplingRates="48000" />\n'
           b'                </mixPort>\n')
    route = b'                <route sink="Aux Device Out" sources="hdmi" type="mix" />\n'
    return data.replace(mix_anchor, mix + mix_anchor, 1).replace(route_anchor, route + route_anchor, 1)


def configure(system, vendor):
    """Patch both overlay layers; the product layer shadows the system layer."""
    components = system / 'lib64/libaudiopolicycomponents.so'
    if components.is_symlink() or hashlib.sha256(components.read_bytes()).hexdigest() != COMPONENTS_SHA256:
        raise ValueError('unregistered framework MULTI_CH mapping')
    paths = [system / layer / str(api) / 'etc/audio_policy_configuration_sec.xml'
             for layer in ('vendor_overlay', 'product/vendor_overlay') for api in range(28, 35)]
    planned = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError('expected a regular donor audio policy in every overlay')
        planned.append((path, policy_patched(path.read_bytes())))
    hal = vendor / 'lib/hw/audio.primary.exynos9820.so'
    if hal.is_symlink() or not hal.is_file():
        raise ValueError('expected the regular HWC1 primary audio HAL')
    original = hal.read_bytes()
    planned.append((hal, patched(original)))
    # Validate every input before writing; retain ownership, mode and xattrs.
    for path, data in planned:
        path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError('HDMI audio write verification failed')
    return {'framework_components_sha256': COMPONENTS_SHA256,
            'multi_ch_flag': 1 << 25,
            'policy_original_sha256': POLICY_SHA256,
            'policy_files': {str(path.relative_to(system)): hashlib.sha256(data).hexdigest()
                             for path, data in planned[:-1]},
            'hal_original_sha256': hashlib.sha256(original).hexdigest(),
            'hal_sha256': PATCHED_SHA256, 'hal_instruction_offset': OFFSET,
            'device_playback_tested': False}


def patched(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA256:
        return data
    if digest != ORIGINAL_SHA256 or data[OFFSET:OFFSET+4] != BEFORE:
        raise ValueError('unregistered audio HAL; refusing version-dependent patch')
    result = data[:OFFSET] + AFTER + data[OFFSET+4:]
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError('unexpected patched audio HAL hash')
    return result


def apply(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('audio HAL must be a regular file')
    # Preserve ownership, mode and xattrs on the work-tree inode.
    with path.open('r+b') as stream:
        source = stream.read()
        result = patched(source)
        if result != source:
            stream.seek(0)
            stream.write(result)
            stream.flush()
    if path.read_bytes() != result:
        raise ValueError('audio HAL write verification failed')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: s10_hdmi_audio.py AUDIO_PRIMARY_EXYNOS9820')
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        sys.exit('S10 HDMI audio: ' + str(exc))
