#!/usr/bin/env python3
"""Targeted root maintenance: add package dispatch, preserve bootstrap/config/live units."""
import hashlib
import json
import os
from pathlib import Path
import stat
from package_support import LAUNCHER, MARKER, extend, available

if os.geteuid() != 0: raise SystemExit('Run this targeted host maintenance as root.')
for path in (LAUNCHER, MARKER.parent):
    info = path.lstat()
    if path.resolve(strict=True) != path or info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('The installed development host paths are not trusted; existing files were preserved.')
before = LAUNCHER.read_text(); after = extend(before)
if before != after:
    temporary = LAUNCHER.with_name('.development-package-launch.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
    try:
        os.fchmod(fd, 0o755)
        with os.fdopen(fd, 'w') as stream:
            stream.write(after); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, LAUNCHER)
    finally:
        if temporary.exists(): temporary.unlink()
value = {'schema': 1, 'packageJobs': 1, 'launcherSha256': hashlib.sha256(LAUNCHER.read_bytes()).hexdigest()}
temporary = MARKER.with_name('.package-support.tmp')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
try:
    os.fchmod(fd, 0o644)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, MARKER)
finally:
    if temporary.exists(): temporary.unlink()
for parent in (LAUNCHER.parent, MARKER.parent):
    fd = os.open(parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
if not available(): raise SystemExit('The package dispatcher qualification failed.')
print('Package worker dispatch qualified. Existing config, service units and running workers/VMs were preserved.')
