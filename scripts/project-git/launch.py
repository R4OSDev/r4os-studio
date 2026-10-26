#!/usr/bin/env python3
"""Fixed root-owned dispatcher. The service is always unprivileged."""
import os
from pathlib import Path

release = Path('/opt/r4os-studio/current').resolve(strict=True)
script = release / 'scripts/project-git/host.py'
if not release.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022:
    raise SystemExit('Git coordinator requires an immutable installed release.')
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(script)])
