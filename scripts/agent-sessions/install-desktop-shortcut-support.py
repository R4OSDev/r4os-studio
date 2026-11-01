#!/usr/bin/env python3
"""Explicit additive v18 updater compatibility; preserve existing host setup."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('desktop_shortcut_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = '00d253c64e0e9ad0840bc3c990b2ace829f0839924718e1c2de4c10b3a34d522'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v18-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='desktop-shortcut-v18')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Desktop shortcut v18 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local desktop shortcut compatibility maintenance as root.')
    install()
