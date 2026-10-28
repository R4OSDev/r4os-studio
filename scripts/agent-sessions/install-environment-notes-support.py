#!/usr/bin/env python3
"""Explicit v13 updater compatibility; retain the existing bootstrap and data."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('environment_notes_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = '4e36822f2d41e545cd5321e588339cacd4daa821d10cdea065eff90fe9eaa469'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v13-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='environment-notes-v13')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Environment notes updater compatibility prepared; existing configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0:
        raise SystemExit('Run explicit local Environment notes compatibility maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt', action='store_true')
    args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v13' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable Environment notes release before adoption.')
        support.adopt()
    else:
        install()
