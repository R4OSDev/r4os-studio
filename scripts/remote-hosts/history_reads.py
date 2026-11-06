"""Bounded display summaries of verified, unchanged local remote job stores."""
from collections import OrderedDict
import json
from pathlib import Path
import stat
import threading
import time
import job_store as jobs

MAX_ENTRIES=64
MAX_BYTES=4*1024**2
TTL=30
QUERY='''SELECT id,request_id,session_id,run_id,host_id,state,phase,payload,
    NULL AS result,created_at,updated_at FROM jobs WHERE host_id=?
    ORDER BY updated_at DESC,id DESC LIMIT 33'''


def generation(projects,project):
    parent=Path(projects).absolute()/project;directory=parent/'RemoteHosts';path=directory/'Jobs.sqlite'
    result=[]
    try:
        for candidate in (parent,directory,path,*[path.with_name(path.name+suffix) for suffix in ('-journal','-wal','-shm')]):
            try:info=candidate.lstat()
            except FileNotFoundError:
                if candidate in (parent,directory,path):return None
                result.append(None);continue
            is_dir=candidate in (parent,directory)
            if candidate.resolve(strict=True)!=candidate or (not stat.S_ISDIR(info.st_mode) if is_dir else not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):return None
            value=[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink]
            if not is_dir:
                value.append(info.st_size)
                if not candidate.name.endswith('-shm'):value.extend((info.st_mtime_ns,info.st_ctime_ns))
            result.append(tuple(value))
        return tuple(result)
    except OSError:return None


def summaries(projects,project,host):
    with jobs.connection(projects,project) as db:
        if db is None:return []
        values=[]
        for row in db.execute(QUERY,(host,)):
            value=jobs.public(row)
            values.append({**{k:value[k] for k in ('id','projectId','sessionId','hostId','hostName','requestId','operation','state','phase','createdAt','updatedAt')},
                'commandPreview':value.get('command','')[:160],'action':value.get('transfer',{}).get('action')})
        return values


class HistoryReads:
    def __init__(self):
        self.entries=OrderedDict();self.bytes=0;self.lock=threading.Lock()

    def read(self,projects,project,host):
        key=(str(Path(projects).absolute()),project,host);before=generation(projects,project)
        with self.lock:
            old=self.entries.get(key)
            if old and before is not None and old['generation']==before and old['expires']>time.monotonic():
                self.entries.move_to_end(key);return old['value']
        value=summaries(projects,project,host)
        after=generation(projects,project)
        # An additive index may have changed the first open. Only a later
        # unchanged fully validated pass is eligible for reuse.
        size=len(json.dumps(value,ensure_ascii=True).encode())
        with self.lock:
            previous=self.entries.pop(key,None)
            if previous:self.bytes-=previous['bytes']
            if before is not None and before==after and size<=MAX_BYTES:
                self.entries[key]={'generation':after,'expires':time.monotonic()+TTL,'value':value,'bytes':size};self.bytes+=size
                while len(self.entries)>MAX_ENTRIES or self.bytes>MAX_BYTES:
                    _,removed=self.entries.popitem(last=False);self.bytes-=removed['bytes']
        return value
