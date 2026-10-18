#!/usr/bin/env python3
"""Resolve current once so all imports stay on the same release during switching."""
import json
import os
from pathlib import Path

base = Path('/opt/r4os-studio')
config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
release = (base / 'current').resolve()
manifest = json.loads((release / 'release.json').read_text())
os.environ['STUDIO_RELEASE_ID'] = manifest['id']
os.chdir(release)
os.execv(config['node'], [config['node'], str(release / 'backend/dist/server.js'), '--serve-frontend'])
