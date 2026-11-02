#!/usr/bin/env python3
"""Explicit additive v20 updater compatibility; preserve existing host setup."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('editor_shortcut_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = 'f9b2504984f5685725978c4ba7f252379d0a7875a42820d7d86d43fb53535a55'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v20-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='editor-shortcut-v20')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Original editor shortcut v20 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local editor shortcut compatibility maintenance as root.')
    install()
