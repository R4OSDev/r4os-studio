#!/usr/bin/env python3
"""Explicit additive v17 updater compatibility; preserve the existing bootstrap."""
import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location('drag_interrupt_host_support', Path(__file__).with_name('install-skill-support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
PREVIOUS_UPDATER = '40fca25d393de88d14824314913777525bf803e7c3789d02d5f1e29a017cd6fe'


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py')
    original, replacement = support.checked(updater, scripts / 'updates/host.py', PREVIOUS_UPDATER, 'v17-compatible updater')
    support.idle_updater()
    support.control('stop', 'r4os-studio-updates.service')
    try:
        support.idle_updater()
        support.replace(updater, replacement, original, stamp='drag-interrupt-v17')
    finally:
        support.control('start', 'r4os-studio-updates.service')
    print('Drag interrupt v17 updater compatibility prepared; configuration, workers and VMs preserved.')


if __name__ == '__main__':
    if os.getuid() != 0: raise SystemExit('Run explicit local drag interrupt compatibility maintenance as root.')
    install()
