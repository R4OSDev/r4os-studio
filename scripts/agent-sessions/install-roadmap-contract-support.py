#!/usr/bin/env python3
"""Explicit v12 updater compatibility; retain the existing bootstrap and data."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('roadmap_contract_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = 'ab770bbb1f6dfb8f4d6ec0166b6062c68da84b7106680202152ab64d55583118'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v12-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='roadmap-contract-v12')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Roadmap v12 updater compatibility prepared; existing configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0:
        raise SystemExit('Run explicit local Roadmap contract compatibility maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt', action='store_true')
    args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v12' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable Roadmap v12 release before adoption.')
        support.adopt()
    else:
        install()
