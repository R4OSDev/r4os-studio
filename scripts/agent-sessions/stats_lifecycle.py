"""Retain only numeric outbox receipts before deleting their source owner."""
from contextlib import closing
from itertools import islice
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from profile import directory,regular,write_json
from stats_store import Source,Statistics,validate
from store import ProjectFault

def preserve_pending(projects,path):
    projects=Path(projects).absolute();path=Path(path)
    if not path.exists():return 0
    if path.resolve(strict=True)!=path.absolute() or not path.is_file():raise ProjectFault('Statistics source could not be retained before deletion.',503)
    with closing(sqlite3.connect(path,timeout=2)) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_receipts'").fetchone():return 0
        try:Source(SimpleNamespace(db=db,projects=projects)).flush()
        except Exception:pass  # The separate numeric outbox survives source deletion.
        rows=db.execute('SELECT payload FROM statistic_receipts WHERE acknowledged=0').fetchall()
        if not rows:return 0
        pending=directory(projects/'.studio/statistics/Pending')
        for row in rows:
            value=validate(json.loads(row[0]));target=pending/(value['key']+'.json')
            if target.exists():
                old=validate(json.loads(regular(target).read_text()))
                if any(old[k]!=value[k] for k in ('kind','key','project','session')):raise ProjectFault('Conflicting numeric retention evidence was preserved.',409)
                if old['kind']=='goal' and old['values']['durationMs']>value['values']['durationMs']:continue
                if old['kind']!='goal' and old['values']!=value['values']:raise ProjectFault('Conflicting numeric retention evidence was preserved.',409)
            write_json(target,value)
        return len(rows)

def flush_pending(projects,limit=128):
    path=Path(projects)/'.studio/statistics/Pending'
    if not path.exists():return 0
    directory(path);items=list(islice(path.glob('*.json'),limit))
    if not items:return 0
    db=Statistics(projects,True);count=0
    try:
        for file in items:
            if regular(file).stat().st_size>4096:raise ProjectFault('Numeric retention receipt is invalid; existing data was preserved.',503)
            value=validate(json.loads(file.read_text()))
            if file.name!=value['key']+'.json':raise ProjectFault('Numeric retention identity changed.',503)
            db.apply(value);file.unlink();count+=1
    finally:db.close()
    return count
