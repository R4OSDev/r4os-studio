#!/usr/bin/env python3
"""Explicit local setup for the private VM release-batch journal."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile

CONFIG = Path('/etc/r4os-studio-updates/config.json')
DROPIN = Path('/etc/systemd/system/r4os-studio.service.d/64-vm-release-batches.conf')


def main():
    if os.geteuid() != 0: raise SystemExit('Run local host setup as Root.')
    print('Root services already have access to their configured data paths. No filesystem grant is needed.')


if __name__ == '__main__': main()
