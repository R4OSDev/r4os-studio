#!/usr/bin/env python3
"""Fixed root-owned dispatcher. All invocations already run as r4os-studio."""
import json
import os
from pathlib import Path
import re
import sys

if len(sys.argv) == 1:
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    name = 'host.py'; extra = []
else:
    ident = sys.argv[1]
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise SystemExit('Invalid run ID.')
    cfg = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    file = Path(cfg['projects']) / '.studio/agents' / ident / 'worker.json'
    if file.resolve(strict=True) != file: raise SystemExit('Invalid worker manifest path.')
    meta = json.loads(file.read_text())
    if meta['runId'] != ident or meta['schema'] != 1 or meta['projects'] != cfg['projects'] or meta['providers'] != cfg['providers'] or meta['r4os'] != cfg['r4os']:
        raise SystemExit('Invalid worker binding.')
    release = Path(meta['releaseRoot']).resolve(strict=True)
    name = 'worker.py'; extra = [str(file)]
    if len(sys.argv) > 2:
        if sys.argv[2] != '--finalize': raise SystemExit('Unsupported worker operation.')
        extra.append('--finalize')
if not release.is_relative_to('/opt/r4os-studio/releases'): raise SystemExit('Invalid agent release.')
script = release / 'scripts/agent-sessions' / name
if script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise SystemExit('Agent release is not immutable.')
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(script), *extra])
