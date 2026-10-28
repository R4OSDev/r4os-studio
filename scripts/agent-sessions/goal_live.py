"""Additive human Live-Play provenance; never rewrite the original Run config."""
import hashlib
import json

from session_store import encode, identity, now
from store import ProjectFault


def digest(value): return hashlib.sha256(encode(value).encode()).hexdigest()


def target(value):
    if (not isinstance(value,dict) or set(value)!={'runId','threadId','turnId'}
            or any(not isinstance(v,str) or not v or len(v.encode())>256 or '\x00' in v for v in value.values())):
        raise ProjectFault('Live Goal control needs its original run, thread and turn.',400)
    identity(value['runId'])
    return value


class LiveGoals:
    def __init__(self,store): self.store=store

    def schema(self):
        # Invoke before the Goal command's BEGIN; binding below shares its commit.
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS goal_activations(
                request_id TEXT PRIMARY KEY REFERENCES goal_commands(request_id),
                session_id TEXT NOT NULL REFERENCES sessions(id),run_id TEXT NOT NULL REFERENCES runs(id),
                binding TEXT NOT NULL,goal TEXT NOT NULL,capture_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL)''')

    def validate(self,sid,data):
        selection=target(data['target']);session=self.store.row(sid)
        row=self.store.db.execute('SELECT * FROM runs WHERE id=? AND session_id=?',(selection['runId'],sid)).fetchone()
        if (not row or not row['busy'] or row['state']!='running' or row['turn_id']!=selection['turnId']
                or session['thread_id']!=selection['threadId'] or data.get('sessionRevision')!=session['revision']):
            raise ProjectFault('The original live Goal target changed or is stopping. The draft was preserved.',409)
        worker=json.loads(row['worker'] or '{}')
        if worker.get('liveGoalPreparation')!=1: raise ProjectFault('This worker has no prepared live Goal capability. Wait for a new compatible run.',503)
        config=json.loads(row['config'])
        if config.get('owner')!={'type':self.store.owner_type,'id':self.store.owner_id}:
            raise ProjectFault('Live Goal target belongs to another owner.',403)
        return row

    def bind(self,sid,data,goal):
        row=self.validate(sid,data)
        if data['action']!='play':return
        if not goal:raise ProjectFault('Save a Goal before pressing Play.',409)
        self.store.db.execute('INSERT INTO goal_activations VALUES (?,?,?,?,?,?,?,?,?)',
            (data['requestId'],sid,row['id'],encode({'owner':{'type':self.store.owner_type,'id':self.store.owner_id},'sessionId':sid,**data['target']}),
             encode(goal),digest(goal),digest(json.loads(row['config'])),'accepted',now()))

    def get(self,sid,request_id):
        self.store.row(sid)
        row=self.store.db.execute('SELECT * FROM goal_activations WHERE request_id=? AND session_id=?',(identity(request_id),sid)).fetchone()
        if not row:raise ProjectFault('Live Goal activation not found.',404)
        return row

    def evidence(self,sid,request_id):
        from goal_store import Goals
        row=self.get(sid,request_id);command=Goals(self.store).command(sid,request_id)
        data=json.loads(command['payload']);client={k:v for k,v in data.items() if not k.startswith('_')}
        goal=json.loads(row['goal']);binding=json.loads(row['binding'])
        run=self.store.db.execute('SELECT config,session_id FROM runs WHERE id=?',(row['run_id'],)).fetchone()
        if (not run or run['session_id']!=sid or data.get('action')!='play'
                or data.get('target')!={k:binding[k] for k in ('runId','threadId','turnId')}
                or binding['owner']!={'type':self.store.owner_type,'id':self.store.owner_id}
                or row['capture_hash']!=digest(goal) or goal!=data.get('_goal')
                or row['config_hash']!=digest(json.loads(run['config']))
                or command['fingerprint']!=digest({'sessionId':sid,**client})):
            raise ProjectFault('The original human Live-Play evidence changed. Nothing was activated.',409)
        return {'requestId':request_id,'binding':binding,'goal':goal,'captureSha256':row['capture_hash'],'commandFingerprint':command['fingerprint']}
