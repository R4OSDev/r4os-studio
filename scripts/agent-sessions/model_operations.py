"""Original direct model calls and process ends in the existing session journal."""
import json
import os
from pathlib import Path

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
    def __init__(self,store):
        self.store=store
        with store.db:store.db.execute('''CREATE TABLE IF NOT EXISTS studio_model_calls(
            run_id TEXT NOT NULL REFERENCES runs(id),request_id TEXT NOT NULL UNIQUE,
            phase TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(run_id,request_id))''')

    def row(self,rid):
        row=self.store.db.execute('SELECT * FROM studio_model_calls WHERE request_id=?',(rid,)).fetchone()
        if not row:raise ProjectFault('The original model call is unavailable.',409)
        return row,json.loads(row['data'])

    def put(self,rid,phase,value):
        with self.store.db:self.store.db.execute('UPDATE studio_model_calls SET phase=?,data=? WHERE request_id=?',(phase,encode(value),rid))

    def begin(self,run_id,rid):
        row=get_run(self.store,run_id);config=json.loads(row['config'])
        data={'runId':run_id,'requestId':rid,'sessionId':row['session_id'],'owner':{'type':self.store.owner_type,'id':self.store.owner_id},
            'selection':{key:config[key] for key in ('providerId','model','effort','apiProvider')},'createdAt':now()}
        with self.store.db:self.store.db.execute('INSERT INTO studio_model_calls VALUES (?,?,?,?)',(run_id,rid,'preparing',encode(data)))

    def process(self,rid,stage,child):
        row,data=self.row(rid)
        if stage=='started':
            if data.get('process'):raise ProjectFault('This model call already owns a process.',409)
            data['process']={'pid':child.pid,'birth':birth(child.pid),'bootId':boot(),'cgroup':cgroup(child.pid)}
            self.put(rid,'dispatching',data)
        else:
            original=data.get('process')
            if not original or original['pid']!=child.pid or child.returncode is None:
                raise ProjectFault('The original model process end is unconfirmed.',503)
            data['processEnd']={'confirmed':True,'observedBy':'original-worker-wait','exitCode':child.returncode,'at':now()}
            self.put(rid,row['phase'],data)

    def finish(self,rid,result=None,error=None,attempted=False):
        row,data=self.row(rid);data['finishedAt']=now();data['attempted']=attempted
        if result is not None:
            data.update(origin=result['origin'],usage=result['usage'],finishReason=result['finishReason'])
            self.put(rid,'completed',data)
        else:
            data['error']={'code':getattr(error,'code','interrupted'),'httpStatus':getattr(error,'http_status',None)}
            self.put(rid,'unknown' if attempted else 'failed',data)

    def reconcile(self,run_id):
        for row in self.store.db.execute('SELECT * FROM studio_model_calls WHERE run_id=?',(run_id,)).fetchall():
            data=json.loads(row['data']);process=data.get('process')
            if process and not data.get('processEnd'):
                if process['bootId']==boot() and alive(process['pid'],process['birth']):return False
                data['processEnd']={'confirmed':True,'observedBy':'original-process-identity-ended','exitCode':None,'at':now()}
            phase=row['phase']
            if phase not in ('completed','failed','unknown'):
                phase='unknown';data['reason']='Original model completion was not received. No request was repeated.'
            self.put(row['request_id'],phase,data)
        return True


def worker_identity():
    return {'runEndProtocol':1,'invocationId':os.environ.get('INVOCATION_ID'), 'bootId':boot(),'cgroup':cgroup(os.getpid())}


def confirm_end(store,manifest,observed):
    """An ended exact unit permits credential release, never reconstructs a reply."""
    row=get_run(store,manifest['runId']);worker=json.loads(row['worker'] or '{}');config=json.loads(row['config'])
    if (row['busy'] or config['engine'].get('kind')!='studio' or worker.get('runEndProtocol')!=1
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
