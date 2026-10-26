#!/usr/bin/env python3
"""Qualify the additive project update profile without changing live worker units."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('skill_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
PREVIOUS = 'e6c0409de14d42361f87593ee2f676e9b36b9f7c292a764b1a69910371abd05f'


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py')
    source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = support.checked(target, source, PREVIOUS, 'update-tool-compatible updater')
    support.idle_updater(); support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater(); support.replace(target, replacement, original, stamp='update-tools-v5')
    finally: support.control('start', 'r4os-studio-updates.service')
    print('Update profile compatibility qualified; existing configuration, worker services, data and VMs preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit update-profile host maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v5' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable update-tool-capable release before adoption.')
        support.adopt()
    else: install()
