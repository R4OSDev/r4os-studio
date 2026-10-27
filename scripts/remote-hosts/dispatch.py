#!/usr/bin/python3
"""Root-owned launcher, executed as the unprivileged remote service user."""
import json
import os
from pathlib import Path

release = Path('/opt/r4os-studio/current').resolve(strict=True)
if not release.is_relative_to('/opt/r4os-studio/releases'): raise SystemExit('Invalid immutable remote worker release.')
metadata = json.loads((release / 'release.json').read_text())
if metadata['id'] != release.name: raise SystemExit('Remote worker release identity changed.')
protocol = json.loads((release / 'shared/remote-host.json').read_text())
if protocol.get('hostProtocol') != 1 or protocol.get('catalogSchema') != 1: raise SystemExit('Remote host support requires explicit compatible maintenance.')
source = release / 'scripts/remote-hosts/host.py'
if source.resolve(strict=True) != source: raise SystemExit('Invalid remote worker source.')
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(source), '/etc/r4os-studio-remote/config.json'])
