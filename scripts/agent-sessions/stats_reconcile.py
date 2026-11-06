"""Plain bounded observations for redundant background numeric reconciliation.

They never acknowledge a receipt or authorize a write. Real work still opens
the original owner/session store under its lifetime gates.
"""
from pathlib import Path
import stat
import time

INTERVAL=30
MAX_OBSERVATIONS=128


def source_facts(path):
    path=Path(path).absolute();facts=[]
    try:
        for candidate in (path.parent,path,*[path.with_name(path.name+suffix) for suffix in ('-journal','-wal','-shm')]):
            try:info=candidate.lstat()
            except FileNotFoundError:
                if candidate in (path,path.parent):return None
                facts.append(None);continue
            if (not stat.S_ISDIR(info.st_mode) if candidate==path.parent else not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):return None
            values=[str(candidate.resolve(strict=True)),info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_size]
            if not candidate.name.endswith('-shm'):values.extend((info.st_mtime_ns,info.st_ctime_ns))
            facts.append(tuple(values))
        return tuple(facts)
    except OSError:return None


def target_hint(projects):
    path=Path(projects)/'.studio/statistics/Statistics.sqlite'
    try:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:return None
        with path.open('rb') as stream:header=stream.read(100)
        if len(header)!=100 or header[:16]!=b'SQLite format 3\0':return None
        return {'identity':(str(path.resolve(strict=True)),info.st_dev,info.st_ino,info.st_mode,info.st_uid),
            'size':info.st_size,'mtime':info.st_mtime_ns,'counter':int.from_bytes(header[24:28],'big')}
    except OSError:return None


def restored(previous,current):
    if previous is None or current is None:return previous!=current
    return (previous['identity']!=current['identity'] or current['size']<previous['size']
            or current['mtime']<previous['mtime'] or current['counter']<previous['counter'])


def pending(store):
    return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_receipts'").fetchone()
        and store.db.execute('SELECT 1 FROM statistic_receipts WHERE acknowledged=0 LIMIT 1').fetchone())


def plan(observation,source,target,active=False):
    observed=time.monotonic()
    sweep=not observation or observation.get('sweeping') or restored(observation.get('target'),target) or observed-observation.get('checked',0)>=INTERVAL
    skip=bool(not active and source is not None and observation and not sweep and observation.get('source')==source)
    return skip,bool(sweep),bool(sweep and (not observation or not observation.get('sweeping') or restored(observation.get('target'),target)))
