"""Original host spawn observation and immutable lifetime budget; never extend."""
import datetime
from pathlib import Path
import time
import uuid

FIELDS=('startedAt','observedAt','endedAt','elapsedMilliseconds','deadlineAt','remainingLifetimeMilliseconds','timing')


def wall():return datetime.datetime.now(datetime.timezone.utc)


def boot():
    try:
        value=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return value if str(uuid.UUID(value))==value else None
    except (OSError,ValueError):return None


def unknown():
    return {**{key:None for key in FIELDS if key!='timing'},'observedAt':wall().isoformat(),
        'timing':{'version':1,'coverage':'unavailable','clock':None,'limitMilliseconds':None,'final':None}}


def retained(value):
    """Only return a frozen original measurement, never derive old file times."""
    proof=value.get('terminalTiming');metadata=value.get('timing')
    if (not isinstance(proof,dict) or proof.get('version')!=1 or proof.get('finished') is not True
            or not isinstance(metadata,dict) or metadata.get('version')!=1 or metadata.get('final') is not True):
        return unknown()
    elapsed=value.get('elapsedMilliseconds')
    if elapsed is not None and (type(elapsed) is not int or not 0<=elapsed<=2**53-1):return unknown()
    if elapsed is not None:
        try:
            if str(uuid.UUID(proof['bootId']))!=proof['bootId']:return unknown()
            start=int(proof['startedMonotonicNanoseconds']);end=int(proof['endedMonotonicNanoseconds'])
            if start<0 or end<start or (end-start)//1_000_000!=elapsed:return unknown()
        except (ValueError,TypeError,KeyError):return unknown()
    # No monotonic arithmetic against the current boot, even after a restart.
    return {**{key:value.get(key) for key in FIELDS},'observedAt':wall().isoformat(),
        'timing':{**metadata,'source':'original-frozen-process-item'}}


class Timing:
    def __init__(self,limit_ms=None):
        self.boot_id=boot();self.start_ns=time.monotonic_ns();self.started_at=wall()
        self.limit_ms=None;self.deadline_ns=None;self.deadline_at=None
        self.end_ns=None;self.ended_at=None;self.finished=False;self.final_elapsed_ms=None;self.end_bound=False
        self.pid=None;self.birth=None
        if limit_ms is not None:self.bind_limit(limit_ms)

    def bind_limit(self,limit_ms):
        if type(limit_ms) is not int or limit_ms<=0:raise ValueError('Invalid original terminal lifetime budget.')
        if self.limit_ms is not None:
            if self.limit_ms!=limit_ms:raise ValueError('The original terminal lifetime budget cannot change.')
            return
        self.limit_ms=limit_ms;self.deadline_ns=self.start_ns+limit_ms*1_000_000
        self.deadline_at=(self.started_at+datetime.timedelta(milliseconds=limit_ms)).isoformat()

    def bind_process(self,process):
        self.pid=getattr(process,'pid',None)
        if type(self.pid) is int and self.pid>0:
            try:self.birth=Path('/proc',str(self.pid),'stat').read_text().rsplit(') ',1)[1].split()[19]
            except (OSError,IndexError):pass

    def bound_clock(self):
        if self.boot_id is None or boot()!=self.boot_id:return None
        current=time.monotonic_ns()
        return current if current>=self.start_ns else None

    def end(self):
        if self.finished:return
        self.finished=True;self.ended_at=wall().isoformat();self.end_ns=self.bound_clock()
        self.end_bound=self.end_ns is not None
        if self.end_bound:self.final_elapsed_ms=(self.end_ns-self.start_ns)//1_000_000

    def remaining_seconds(self):
        # Enforce the original monotonic budget independently of display proof.
        return None if self.deadline_ns is None else max(0,(self.deadline_ns-time.monotonic_ns())/1_000_000_000)

    def public(self):
        current=None if self.finished else self.bound_clock()
        elapsed=self.final_elapsed_ms if self.finished else ((current-self.start_ns)//1_000_000 if current is not None else None)
        remaining=(None if self.limit_ms is None else 0 if self.finished else
            max(0,(self.deadline_ns-current)//1_000_000) if current is not None else None)
        return {'startedAt':self.started_at.isoformat(),'observedAt':wall().isoformat(),'endedAt':self.ended_at,
            'elapsedMilliseconds':elapsed,'deadlineAt':self.deadline_at,'remainingLifetimeMilliseconds':remaining,
            'timing':{'version':1,'coverage':'host-observed-lifetime' if elapsed is not None else 'unavailable',
                'measurement':'spawn-invocation-to-observed-exit','clock':'host-monotonic',
                'bootBound':self.end_bound if self.finished else current is not None,'limitMilliseconds':self.limit_ms,
                'final':self.finished}}

    def proof(self):
        return {'version':1,'bootId':self.boot_id,'pid':self.pid,'processBirthTicks':self.birth,
            'startedMonotonicNanoseconds':str(self.start_ns),
            'deadlineMonotonicNanoseconds':str(self.deadline_ns) if self.deadline_ns is not None else None,
            'endedMonotonicNanoseconds':str(self.end_ns) if self.end_ns is not None else None,'finished':self.finished}
