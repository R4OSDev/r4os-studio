#!/usr/bin/env python3
"""Qualify the additive author tool profile without changing live worker units."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('skill_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
PREVIOUS = 'b13a8720cf789864649d5c79aaf39f05ad60a316e6ba81cc1582af0137cc9757'


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py')
    source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = support.checked(target, source, PREVIOUS, 'author-compatible updater')
    support.idle_updater(); support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater(); support.replace(target, replacement, original, stamp='skill-authors')
    finally: support.control('start', 'r4os-studio-updates.service')
    print('Author profile compatibility qualified; existing configuration, worker services, data and VMs preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit author-profile host maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-skill-tools-v2' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []):
            raise SystemExit('Install the immutable author-capable release before adoption.')
        support.adopt()
    else: install()
