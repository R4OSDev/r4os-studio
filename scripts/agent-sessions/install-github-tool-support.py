#!/usr/bin/env python3
"""Explicit additive GitHub-tool profile compatibility; preserve bootstrap and live workers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('skill_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
PREVIOUS = '4487a19a5c36f5fbd0c3c174fba3775deaf16915ae9509145fd27657087fdfc9'


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py'); source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = support.checked(target, source, PREVIOUS, 'GitHub-tool-compatible updater')
    support.idle_updater(); support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater(); support.replace(target, replacement, original, stamp='github-tools-v6')
    finally: support.control('start', 'r4os-studio-updates.service')
    print('GitHub profile compatibility qualified; existing configuration, workers, history and VMs preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit GitHub-profile maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    if args.adopt:
        release = Path('/opt/r4os-studio/current').resolve(strict=True)
        if 'studio-tools-v6' not in json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', []): raise SystemExit('Install the immutable GitHub-tool release before adoption.')
        support.adopt()
    else: install()
