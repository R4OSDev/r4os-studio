#!/usr/bin/env python3
"""Explicit v9 compatibility maintenance; existing protocols and data preserved."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('existing_remote_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
PREVIOUS = '56085599c28eaeb86375d0e09f512a3beec60877c382848f83f6d0b817f2073f'


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py'); source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = support.checked(target, source, PREVIOUS, 'Remote-tool-compatible updater')
    support.idle_updater(); support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater(); support.replace(target, replacement, original, stamp='remote-tools-v9')
    finally: support.control('start', 'r4os-studio-updates.service')
    print('Additive v9 compatibility prepared; updater configuration, worker bindings and VMs preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit Remote Host profile maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v9' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable v9 release before adoption.')
        support.adopt()
    else: install()
