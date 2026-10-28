#!/usr/bin/env python3
"""Fixed root-owned dispatcher. All invocations already run as r4os-studio."""
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from contextlib import closing

def attachment_guard(meta,release):
    kind=meta.get('ownerType','project');owner=meta.get('ownerId') if 'ownerType' in meta else meta['projectId']
    root=Path(meta['projects']).parent/'Skills' if kind=='skill' else Path(meta['projects'])
    path=root/owner/'Sessions/Sessions.sqlite'
    if not path.exists():return
    if path.resolve(strict=True)!=path or not stat.S_ISREG(path.lstat().st_mode):raise SystemExit('Invalid native attachment catalog.')
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='attachment_refs'").fetchone():return
            images=db.execute("SELECT 1 FROM attachment_refs WHERE session_id=? AND json_extract(frozen,'$.mode')='localImage' LIMIT 1",(meta['sessionId'],)).fetchone()
        if images and not (release/'scripts/agent-sessions/image_inputs.py').is_file():
            raise SystemExit('This release cannot resume the native image conversation. Original history and attachments were preserved.')
    except sqlite3.Error:raise SystemExit('Native attachment history could not be checked. No model was started.') from None


def main():
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
        if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',str(meta.get('sessionId',''))):raise SystemExit('Invalid worker session binding.')
        if meta['runId'] != ident or meta['schema'] != 1 or meta['projects'] != cfg['projects'] or meta['providers'] != cfg['providers'] or meta['r4os'] != cfg['r4os']:
            raise SystemExit('Invalid worker binding.')
        kind = meta.get('ownerType', 'project')
        owner = meta.get('ownerId') if 'ownerType' in meta else meta.get('projectId')
        if (kind not in ('project', 'skill') or not isinstance(owner, str)
                or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', owner)
                or (kind == 'skill' and 'projectId' in meta) or (kind == 'project' and meta.get('projectId', owner) != owner)):
            raise SystemExit('Invalid worker owner binding.')
        release = Path(meta['releaseRoot']).resolve(strict=True)
        name = 'worker.py'; extra = [str(file)]
        if len(sys.argv) > 2:
            if sys.argv[2] != '--finalize': raise SystemExit('Unsupported worker operation.')
            extra.append('--finalize')
    if not release.is_relative_to('/opt/r4os-studio/releases'): raise SystemExit('Invalid agent release.')
    script = release / 'scripts/agent-sessions' / name
    if script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise SystemExit('Agent release is not immutable.')
    if name=='worker.py' and '--finalize' not in extra:attachment_guard(meta,release)
    os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(script), *extra])


if __name__=='__main__':main()
