#!/usr/bin/env python3
"""Installed root-owned launcher; execute the selected manager as an unprivileged service."""
import os
from pathlib import Path

release = Path('/opt/r4os-studio/current').resolve(strict=True)
if not release.is_relative_to('/opt/r4os-studio/releases'):
    raise SystemExit('Invalid Studio release.')
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(release / 'scripts/components/service.py')])
