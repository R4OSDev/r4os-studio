#!/usr/bin/env python3
"""Root-owned stable entry point; one unit instance selects one private original job."""
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys


def main():
    if len(sys.argv) != 2 or not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', sys.argv[1]):
        raise SystemExit('Invalid source job instance.')
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    root = Path(config['projects']).parent / 'Skills'
    db_path = root / 'Skills.sqlite'
    if db_path.resolve(strict=True) != db_path or not stat.S_ISREG(db_path.stat().st_mode):
        raise SystemExit('Invalid skill source catalog.')
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT skill_id,metadata FROM skill_source_jobs WHERE request_id=?', (sys.argv[1],)).fetchone()
    if not row or not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', row[0]):
        raise SystemExit('The original source job is unavailable.')
    if json.loads(row[1]).get('phase') != 'queued':
        return
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    if not release.is_relative_to('/opt/r4os-studio/releases'):
        raise SystemExit('Invalid installed source worker release.')
    script = release / 'scripts/skills/source_worker.py'
    info = script.stat()
    if script.resolve(strict=True) != script:
        raise SystemExit('The installed source worker changed.')
    os.execve('/usr/bin/python3', ['/usr/bin/python3', '-B', str(script), str(root), row[0], sys.argv[1]],
              {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'STUDIO_SOURCE_INVOCATION': os.environ.get('INVOCATION_ID', '')})


if __name__ == '__main__':
    main()
