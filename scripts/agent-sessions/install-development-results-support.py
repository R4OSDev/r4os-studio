#!/usr/bin/env python3
"""Explicit additive v15 updater compatibility; never reinitialize bootstrap."""
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('gesture_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = 'aa1c189a6c318d8222b4630d093bd2a31caba25c77f98a7c19b634c21cf05874'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v15-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='development-results-v15')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Development-results v15 updater compatibility prepared; existing configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local development-results compatibility maintenance as root.')
    install()
