#!/usr/bin/env python3
"""Explicit layout maintenance, as the owner of the persistent Projects directory."""
import argparse
import fcntl
import json
import os
from pathlib import Path
from store import connect, operation
from layout import migrate, folder

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('project_id')
parser.add_argument('--rollback', action='store_true')
args = parser.parse_args()
os.umask(0o077)
root = Path(os.environ.get('STUDIO_R4OS_DIR') or Path(__file__).resolve().parents[2] / 'Data/R4OS').resolve()
projects = root.parent / 'Projects'
folder(projects / '.studio')
with (projects / '.studio/create.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    with connect(projects) as db:
        operation(db, {'operation': 'get', 'id': args.project_id}, root)
    with (projects / '.studio' / ('workspace-' + args.project_id + '.lock')).open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(migrate(projects, args.project_id, args.rollback)))
