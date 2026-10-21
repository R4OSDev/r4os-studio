#!/usr/bin/python3
"""OpenSSH asks through a private runtime file; secrets never enter argv/env."""
import os
from pathlib import Path
import re
import sys

request_id = os.environ.get('STUDIO_ACCESS_REQUEST', '')
if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', request_id): sys.exit(1)
path = Path('/run/r4os-studio-development/auth') / request_id / 'password'
if path.resolve(strict=True) != path or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077: sys.exit(1)
sys.stdout.write(path.read_text() + '\n')
