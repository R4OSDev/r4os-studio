#!/usr/bin/env python3
"""Root-owned fixed dispatcher; all processes already run unprivileged."""
import json
import os
from pathlib import Path
import re
import sys

if len(sys.argv) == 1:
    release = Path('/opt/r4os-studio/current').resolve(strict=True); name = 'host.py'; extra = []
else:
    ident = sys.argv[1]
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise SystemExit('Invalid development job ID.')
    cfg = json.loads(Path('/etc/r4os-studio-development/config.json').read_text())
    path = Path(cfg['projects']) / '.studio/development' / ident / 'worker.json'
    if path.resolve(strict=True) != path: raise SystemExit('Invalid worker metadata path.')
    meta = json.loads(path.read_text())
    if meta['schema'] != 1 or meta['jobId'] != ident or any(meta[k] != cfg[k] for k in ('projects', 'r4os')):
        raise SystemExit('Invalid development worker binding.')
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', meta['projectId']): raise SystemExit('Invalid project ID.')
    release = Path(meta['releaseRoot']).resolve(strict=True)
    name = 'worker.py' if meta.get('kind', 'build') in ('build', 'package') else 'vm_worker.py'
    extra = [str(path)]
    if len(sys.argv) > 2:
        if sys.argv[2:] != ['--finalize']: raise SystemExit('Unsupported worker operation.')
        extra.append('--finalize')
if not release.is_relative_to('/opt/r4os-studio/releases'): raise SystemExit('Invalid development release.')
script = release / 'scripts/project-development' / name
if script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise SystemExit('Development release is not immutable.')
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(script), *extra])
