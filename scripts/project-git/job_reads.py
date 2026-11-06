"""Small derived last-job projections; original files remain authoritative."""
from collections import OrderedDict
import json
from pathlib import Path
import stat
import threading
import time
from common import ProjectFault, document

READS = ('status', 'check', 'diff')
MAX_ENTRIES = 64
MAX_BYTES = 4 * 1024**2
TTL = 5


def facts(path, directory=False):
    try:
        path=Path(path); info=path.lstat()
        if path.resolve(strict=True)!=path or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):return None
        return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    except OSError:return None


class LastJobs:
    def __init__(self, base, public):
        self.base=base;self.public=public;self.entries=OrderedDict();self.bytes=0
        self.lock=threading.Lock();self.epoch=0

    def invalidate(self, project):
        with self.lock:
            old=self.entries.pop(project,None)
            if old:self.bytes-=old['bytes']
            self.epoch+=1

    def read(self, project):
        for _ in range(2):
            with self.lock:old=self.entries.get(project);epoch=self.epoch
            generation=facts(self.base,True)
            if (old and generation is not None and old['generation']==generation and old['expires']>time.monotonic()
                    and (old['path'] is None or old['facts'] is not None and facts(old['path'])==old['facts'])):
                with self.lock:
                    if epoch!=self.epoch:continue
                    if project in self.entries:self.entries.move_to_end(project)
                    return old['value']
            winner=None;rank=None;path=None
            for directory in self.base.iterdir():
                candidate=document(directory/'job.json')
                if candidate['projectId']!=project:continue
                action=candidate['kind'] not in READS
                priority=(2 if action and candidate['state']=='unknown' else 1 if action else 0,candidate['createdAt'])
                if rank is None or priority>rank:winner=candidate;rank=priority;path=directory/'job.json'
            value=self.public(winner) if winner else None
            # Re-read the selected original so a worker finishing during the
            # scan cannot leave its former unknown state in a warm projection.
            selected=facts(path) if path else None
            if path:
                current=document(path)
                if current!=winner:continue
            if generation is None or generation!=facts(self.base,True) or path and selected!=facts(path):continue
            size=len(json.dumps(value,ensure_ascii=True).encode())
            with self.lock:
                if epoch!=self.epoch:continue
                previous=self.entries.pop(project,None)
                if previous:self.bytes-=previous['bytes']
                if size<=MAX_BYTES and (path is None or selected is not None):
                    self.entries[project]={'generation':generation,'path':path,'facts':selected,'value':value,
                        'expires':time.monotonic()+TTL,'bytes':size};self.bytes+=size
                    while len(self.entries)>MAX_ENTRIES or self.bytes>MAX_BYTES:
                        _,removed=self.entries.popitem(last=False);self.bytes-=removed['bytes']
                return value
        raise ProjectFault('Git history changed during inspection. Read the original jobs again shortly.',409)
