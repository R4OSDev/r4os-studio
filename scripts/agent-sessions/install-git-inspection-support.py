#!/usr/bin/env python3
"""Explicit additive v22 updater compatibility; preserve existing host setup."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('git_inspection_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = '6537f8fec7b0ce54f4705bab97fbd15b656c014a0c30efa6c4922ef8e9cec7a5'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v22-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='git-inspection-v22')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Original Git inspection v22 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local Git inspection compatibility maintenance as root.')
    install()
