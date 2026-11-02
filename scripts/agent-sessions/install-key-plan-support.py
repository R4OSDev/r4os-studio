#!/usr/bin/env python3
"""Explicit additive v21 updater compatibility; preserve existing host setup."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('key_plan_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = 'fcd60077aae3ef0b0d0a400e534bb635f82bc01ce2ccea5ec8393ae393115e53'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v21-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='key-plan-v21')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Original key plan v21 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local key plan compatibility maintenance as root.')
    install()
