"""Small original-source context snapshots; no transcript scan or inference."""
import json

from profile import CODEX_VERSION,CODEX_SHA256
from session_store import encode,now

SOURCE='codex-0.163.0/thread/tokenUsage/updated:last'
FIELDS=('totalTokens','inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens','reasoningOutputTokens')


def qualified(engine):
    return (not engine.get('api') and engine.get('kind')!='claude-code'
        and engine.get('version')==CODEX_VERSION and engine.get('sha256')==CODEX_SHA256)


def number(value,positive=False):return type(value) is int and (1 if positive else 0)<=value<=2**53-1


def saved(store,sid):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_context'").fetchone():return None
    row=store.db.execute('SELECT payload FROM session_context WHERE session_id=?',(sid,)).fetchone()
    return json.loads(row[0]) if row else None


def empty(store,row):
    engine=json.loads(row['engine']);settings=json.loads(row['settings'])
    return {'schema':1,'revision':0,'owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':row['id'],
        'engine':'claude-code' if engine.get('kind')=='claude-code' else 'codex',
        'engineVersion':engine.get('version'),'engineSha256':engine.get('sha256'),
        'providerId':settings['providerId'],'requestedModel':settings['model'],'model':None,'modelProvider':None,
        'threadId':row['thread_id'],'runId':None,'turnId':None,'source':None,'reportedAt':None,
        'state':'unavailable','reason':'This engine has no qualified context measurement.' if not qualified(engine)
            else 'No context measurement has been reported by this worker.',
        'usedTokens':None,'capacityTokens':None,'remainingTokens':None,'overflowTokens':None,'usedRatio':None,
        'last':None,'autoCompactThreshold':None,'nominalModelCapacity':None}


def read(store,row):
    """Read only one bounded row. Selection changes never relabel old tokens."""
    current=empty(store,row);snapshot=saved(store,row['id'])
    if not snapshot:return current
    if any(snapshot.get(k)!=current[k] for k in ('owner','sessionId','engine','engineVersion','engineSha256','providerId','requestedModel','threadId')):
        return {**snapshot,'state':'pending','reason':'The selection or native conversation changed. Waiting for a matching context measurement.'}
    latest=store.db.execute('SELECT id,busy,state,config FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(row['id'],)).fetchone()
    if latest and latest['state']=='unknown':
        return {**snapshot,'state':'stale','reason':'The latest native execution is unconfirmed. This is the last measured context.'}
    if latest and latest['id']!=snapshot['runId']:
        config=json.loads(latest['config'])
        if config.get('contextProtocol')!=1:
            return {**snapshot,'state':'stale','reason':'The latest worker does not report qualified context. This is an earlier measurement.'}
    return snapshot


class Context:
    def __init__(self,worker):
        self.w=worker;self.turn=None;self.seen_turns=set();self.model=None;self.model_provider=None;self.compacting=False

    def active(self):
        w=self.w
        if not qualified(w.config['engine']):return False
        session=w.store.row(w.session_id);settings=json.loads(session['settings'])
        if (not w.thread_id or session['thread_id']!=w.thread_id or not qualified(json.loads(session['engine']))
            or any(settings[k]!=w.config[k] for k in ('providerId','model'))):return False
        row=w.store.db.execute('SELECT id,busy FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(w.session_id,)).fetchone()
        return bool(row and row['id']==w.run_id and row['busy'])

    def write(self,value):
        w=self.w;old=saved(w.store,w.session_id)
        content={k:v for k,v in value.items() if k not in ('revision','reportedAt')}
        previous={k:v for k,v in (old or {}).items() if k not in ('revision','reportedAt')}
        if content==previous:return
        value={**value,'revision':(old or {}).get('revision',0)+1}
        from run_store import event
        with w.store.db:
            w.store.db.execute('CREATE TABLE IF NOT EXISTS session_context(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,payload TEXT NOT NULL)')
            w.store.db.execute('INSERT INTO session_context VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload',(w.session_id,encode(value)))
            event(w.store,w.session_id,w.run_id,'context',value,False)

    def invalidate(self,reason,state='stale'):
        if not self.active():return
        w=self.w;value=saved(w.store,w.session_id) or empty(w.store,w.store.row(w.session_id))
        self.write({**value,'state':state,'reason':reason})

    def native(self,response):
        """Bind model/provider from the actual native start/resume reply."""
        if not self.active():return
        if not isinstance(response,dict) or response.get('thread',{}).get('id')!=self.w.thread_id:return
        model=response.get('model');provider=response.get('modelProvider')
        if not all(isinstance(v,str) and 0<len(v)<=200 and not any(ord(c)<32 for c in v) for v in (model,provider)):return
        self.model=model;self.model_provider=provider
        old=saved(self.w.store,self.w.session_id)
        if old and (old['model']!=model or old['modelProvider']!=provider):
            self.invalidate('The native model changed. Waiting for its own context measurement.','pending')

    def notify(self,method,params):
        w=self.w
        if not self.active() or params.get('threadId')!=w.thread_id:return
        if method=='turn/started':
            turn=params.get('turn',{}).get('id')
            if isinstance(turn,str) and 0<len(turn)<=200 and (turn==self.turn or turn not in self.seen_turns):
                self.turn=turn;self.seen_turns.add(turn)
            return
        turn=params.get('turnId')
        if not self.turn or turn!=self.turn:return
        if method=='model/rerouted':
            model=params.get('toModel')
            if isinstance(model,str) and 0<len(model)<=200 and not any(ord(c)<32 for c in model):self.model=model
            else:self.model=None
            self.invalidate('The native model was rerouted. Waiting for a matching window.','pending');return
        if method in ('item/started','item/completed') and params.get('item',{}).get('type')=='contextCompaction':
            self.compacting=method=='item/started'
            self.invalidate('Compaction changed the conversation. Waiting for its next measured context.');return
        if method!='thread/tokenUsage/updated':return
        data=params.get('tokenUsage');last=data.get('last') if isinstance(data,dict) else None
        if not self.model or not isinstance(last,dict) or not number(last.get('totalTokens')):
            self.invalidate('The native context measurement is incomplete.');return
        if any(v is not None and not number(v) for v in (last.get(k) for k in FIELDS)):
            self.invalidate('The native context counter shape could not be confirmed.');return
        if self.compacting:
            self.invalidate('Compaction is still in progress. Waiting for a measured result.');return
        capacity=data.get('modelContextWindow');valid=number(capacity,True);used=last['totalTokens']
        value=empty(w.store,w.store.row(w.session_id))
        value.update(source=SOURCE,reportedAt=now(),runId=w.run_id,turnId=self.turn,
            model=self.model,modelProvider=self.model_provider,state='available' if valid else 'unavailable',
            reason='Last reported native context.' if valid else 'The native effective context window is unknown or invalid.',
            usedTokens=used,capacityTokens=capacity if valid else None,
            remainingTokens=max(0,capacity-used) if valid else None,overflowTokens=max(0,used-capacity) if valid else None,
            usedRatio=used/capacity if valid else None,last={k:last.get(k) for k in FIELDS})
        self.write(value)
