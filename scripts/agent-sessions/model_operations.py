"""Original direct model calls and process ends in the existing session journal."""
import json
import os
from pathlib import Path
import time

from attachment_store import birth
from run_store import get_run
from session_store import encode, now
from store import ProjectFault
from owner import binding


def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def cgroup(pid):
    return next(line[3:] for line in Path('/proc',str(pid),'cgroup').read_text().splitlines() if line.startswith('0::'))


def alive(pid,started):
    try:return birth(pid)==started
    except (OSError,ValueError):return False


class Operations:
    RAW_BATCH_EVENTS=64
    RAW_BATCH_BYTES=256*1024
    RAW_BATCH_SECONDS=0.1

    def __init__(self,store):
        self.store=store
        self.raw_remaining={}
        self.raw_pending={}
        with store.db:store.db.execute('''CREATE TABLE IF NOT EXISTS studio_model_calls(
            run_id TEXT NOT NULL REFERENCES runs(id),request_id TEXT NOT NULL UNIQUE,
            phase TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(run_id,request_id))''')

    def wire(self,rid,raw):
        if rid not in self.raw_pending:
            row,data=self.row(rid)
            with self.store.db:self.store.db.execute('''CREATE TABLE IF NOT EXISTS studio_model_events(
                run_id TEXT NOT NULL REFERENCES runs(id),request_id TEXT NOT NULL REFERENCES studio_model_calls(request_id),
                seq INTEGER NOT NULL,raw TEXT NOT NULL,PRIMARY KEY(request_id,seq))''')
            from session_budgets import total as budget_total
            with self.store.db:used=budget_total(self.store.db,data['sessionId'],'raw')
            self.raw_remaining[rid]=max(0,96*1024*1024-used)
            seq=self.store.db.execute('SELECT COALESCE(MAX(seq),0) FROM studio_model_events WHERE request_id=?',(rid,)).fetchone()[0]
            self.raw_pending[rid]={'runId':row['run_id'],'seq':seq,'events':[],'bytes':0,'since':None}
        pending=self.raw_pending[rid]
        size=len(raw.encode())
        if size>self.raw_remaining[rid]:
            self.flush(rid)
            row,data=self.row(rid)
            if not data.get('rawTruncated'):data['rawTruncated']=True;self.put(rid,row['phase'],data)
            self.raw_remaining[rid]=0;return
        if pending['events'] and pending['bytes']+size>self.RAW_BATCH_BYTES:self.flush(rid)
        if not pending['events']:pending['since']=time.monotonic()
        pending['seq']+=1
        pending['events'].append((pending['runId'],rid,pending['seq'],raw))
        pending['bytes']+=size
        self.raw_remaining[rid]-=size
        if len(pending['events'])>=self.RAW_BATCH_EVENTS or pending['bytes']>=self.RAW_BATCH_BYTES or self.flush_delay(rid)==0:
            self.flush(rid)

    def flush_delay(self,rid):
        pending=self.raw_pending.get(rid)
        return max(0,self.RAW_BATCH_SECONDS-(time.monotonic()-pending['since'])) if pending and pending['events'] else None

    def flush(self,rid):
        pending=self.raw_pending.get(rid)
        if not pending or not pending['events']:return
        # Clear only after a successful FULL commit. A failed write cannot
        # produce a confirmed response or admit a tool from this operation.
        with self.store.db:
            self.store.db.executemany('INSERT INTO studio_model_events VALUES (?,?,?,?)',pending['events'])
        pending['events'].clear();pending['bytes']=0;pending['since']=None

    def row(self,rid):
        row=self.store.db.execute('SELECT * FROM studio_model_calls WHERE request_id=?',(rid,)).fetchone()
        if not row:raise ProjectFault('The original model call is unavailable.',409)
        return row,json.loads(row['data'])

    def put(self,rid,phase,value):
        with self.store.db:self.store.db.execute('UPDATE studio_model_calls SET phase=?,data=? WHERE request_id=?',(phase,encode(value),rid))

    def begin(self,run_id,rid,child=None,purpose='conversation',summary_budget=None):
        row=get_run(self.store,run_id);config=json.loads(row['config'])
        if child is not None:
            if child.get('purpose') not in ('vision','image-generation') or child.get('parentRunId') != run_id or child['snapshot']['apiRunId'] != rid: raise ProjectFault('Invalid image operation binding.',409)
            config = child['snapshot']
        data={'runId':run_id,'requestId':rid,'sessionId':row['session_id'],'owner':{'type':self.store.owner_type,'id':self.store.owner_id},
            'purpose':child['purpose'] if child else purpose,
            'selection':{key:config[key] for key in ('providerId','model','effort','apiProvider')},'createdAt':now()}
        if child is not None: data['vision' if child['purpose']=='vision' else 'imageGeneration'] = child
        if purpose=='summary' and summary_budget is not None:data['summaryBudget']=summary_budget
        with self.store.db:self.store.db.execute('INSERT INTO studio_model_calls VALUES (?,?,?,?)',(run_id,rid,'preparing',encode(data)))

    def observe(self,model,rid, *, projection=None):
        """One observer contract for main, summary, vision and image requests."""
        from request_capture import capture,transport
        model.capture_observer=lambda raw,binding,policy,estimate:capture(self.store,self.row(rid)[1],raw,binding,policy,estimate,projection=projection)
        def blocked(raw,binding,policy,estimate,error):
            capture(self.store,self.row(rid)[1],raw,binding,policy,estimate,blocked=error,projection=projection)
            model.blocked_request_id=rid
        model.blocked_observer=blocked
        model.request_observer=lambda stage,status=None:transport(self.store,rid,stage,status)
        model.process_observer=lambda stage,child:self.process(rid,stage,child,model.request_sha256,model.stream_progress)
        model.event_observer=lambda raw:self.wire(rid,raw)
        model.flush_observer=lambda:self.flush(rid)
        model.flush_delay=lambda:self.flush_delay(rid)

    def process(self,rid,stage,child,request_sha256=None,stream_progress=None):
        row,data=self.row(rid)
        if stage=='started':
            if data.get('process'):raise ProjectFault('This model call already owns a process.',409)
            data['process']={'pid':child.pid,'birth':birth(child.pid),'bootId':boot(),'cgroup':cgroup(child.pid)}
            data['requestSha256']=request_sha256
            self.put(rid,'dispatching',data)
        else:
            original=data.get('process')
            if not original or original['pid']!=child.pid or child.returncode is None:
                raise ProjectFault('The original model process end is unconfirmed.',503)
            data['processEnd']={'confirmed':True,'observedBy':'original-worker-wait','exitCode':child.returncode,'at':now()}
            if stream_progress is not None: data['stream'] = stream_progress
            self.put(rid,row['phase'],data)

    def finish(self,rid,result=None,error=None,attempted=False):
        from public_stream import flush as flush_public
        flush_public(self.store)
        self.flush(rid)
        row,data=self.row(rid);data['finishedAt']=now();data['attempted']=attempted
        if result is not None:
            data.update(origin=result['origin'],usage=result['usage'],finishReason=result['finishReason'])
            self.put(rid,'completed',data)
        else:
            data['error']={'code':getattr(error,'code','interrupted'),'httpStatus':getattr(error,'http_status',None)}
            data['error']['category']=getattr(error,'category','interrupted')
            data['error']['details']=getattr(error,'details',None)
            data['error']['partial']=getattr(error,'partial',None)
            if getattr(error,'stream_interrupted',False): data['error']['earlyStreamInterruption'] = True
            proof=getattr(error,'quota_evidence',None)
            if proof and proof.get('kind')=='confirmed-primary-quota' and not data.get('vision') and not data.get('imageGeneration'):
                data['quotaEvidence']=proof
                if not attempted:data['processEnd']={'confirmed':True,'observedBy':'not-dispatched','at':now()}
                self.put(rid,'failed',data)
            elif (getattr(error,'confirmed_overload',False) and attempted
                    and data.get('processEnd',{}).get('confirmed') is True):
                data['error']['confirmedOverload']=True
                self.put(rid,'failed',data)
            else:self.put(rid,'unknown' if attempted else 'failed',data)
        from studio_usage import record
        record(self.store,self.row(rid)[0])
        self.raw_pending.pop(rid,None);self.raw_remaining.pop(rid,None)

    def reconcile(self,run_id):
        for row in self.store.db.execute('SELECT * FROM studio_model_calls WHERE run_id=?',(run_id,)).fetchall():
            data=json.loads(row['data']);process=data.get('process')
            if process and not data.get('processEnd'):
                if process['bootId']==boot() and alive(process['pid'],process['birth']):return False
                data['processEnd']={'confirmed':True,'observedBy':'original-process-identity-ended','exitCode':None,'at':now()}
            phase=row['phase']
            if phase not in ('completed','failed','unknown'):
                phase='unknown';data['reason']='Original model completion was not received. No request was repeated.'
                if not process:data['attempted']=False;phase='failed'
            self.put(row['request_id'],phase,data)
        return True


def worker_identity():
    return {'runEndProtocol':1,'invocationId':os.environ.get('INVOCATION_ID'), 'bootId':boot(),'cgroup':cgroup(os.getpid())}


def confirm_end(store,manifest,observed,auxiliary=False):
    """An ended exact unit permits credential release, never reconstructs a reply."""
    row=get_run(store,manifest['runId']);worker=json.loads(row['worker'] or '{}');config=json.loads(row['config'])
    if (row['busy'] or not auxiliary and config['engine'].get('kind')!='studio' or worker.get('runEndProtocol')!=1
            or row['session_id']!=manifest['sessionId'] or worker.get('release')!=manifest['release']
            or binding(manifest)!=(store.owner_type,store.owner_id)
            or {'type':store.owner_type,'id':store.owner_id}!=config.get('owner')):return False
    if worker.get('processEnd',{}).get('confirmed'):return True
    reboot=worker.get('bootId')!=boot()
    original_group=worker.get('cgroup')
    if not isinstance(original_group,str) or not original_group.startswith('/') or '..' in Path(original_group).parts:return False
    path=Path('/sys/fs/cgroup')/original_group.lstrip('/')
    collected=observed.get('InvocationID')=='' and observed.get('ExecMainPID')=='0' and not path.exists()
    if (observed.get('ActiveState') not in ('inactive','failed') or observed.get('MainPID')!='0'
            or not worker.get('invocationId')
            or not (observed.get('InvocationID')==worker['invocationId'] and observed.get('ExecMainPID')==str(worker.get('pid'))
                or reboot and observed.get('InvocationID')=='' and observed.get('ExecMainPID') in ('0',str(worker.get('pid')))
                or collected)
            or worker['bootId']==boot() and alive(worker.get('pid'),worker.get('birth'))):return False
    group=observed.get('ControlGroup')
    if group and group!=worker.get('cgroup'):return False
    if path.exists() and 'populated 0' not in (path/'cgroup.events').read_text().splitlines():return False
    if not Operations(store).reconcile(row['id']):return False
    proof={'confirmed':True,'observedBy':'original-unit-and-process-end','at':now(),'unit':observed,'replayed':False}
    worker['processEnd']=proof
    with store.db:store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(worker),row['id']))
    return True
