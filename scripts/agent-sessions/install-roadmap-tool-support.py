#!/usr/bin/env python3
"""Explicit v8 compatibility maintenance, preserving older rollback profiles."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('existing_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
PREVIOUS = '01871cba7657216f9eada6aff6d4c0907711432e6b83f640940d9ef033159ca6'


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py')
    source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = support.checked(target, source, PREVIOUS, 'Roadmap-compatible updater')
    support.idle_updater(); support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater(); support.replace(target, replacement, original, stamp='roadmap-tools-v8')
    finally: support.control('start', 'r4os-studio-updates.service')
    print('Roadmap profile compatibility installed; configuration, live workers and VMs preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit Roadmap profile maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v8' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable Roadmap tool release before adoption.')
        support.adopt()
    else: install()
