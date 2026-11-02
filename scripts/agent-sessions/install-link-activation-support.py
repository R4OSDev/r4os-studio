#!/usr/bin/env python3
"""Explicit additive v23 updater compatibility; preserve existing host setup."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('link_activation_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = '755b60ebe3ca02104c8f4bc3ab3bc7d61e9aaf2ef954674253959eaa3b612608'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v23-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='link-activation-v23')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Original native link activation v23 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local native link activation compatibility maintenance as root.')
    install()
