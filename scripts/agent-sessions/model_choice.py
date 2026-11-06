"""Durable next-run model choices. An accepted run is never edited or stopped."""
import hashlib
import json
from skill_lifecycle import guarded
from session_store import encode,identity,now,validate_settings,provider_models
from store import ProjectFault

FIELDS=('model','effort','fastMode')
OPEN=('pending','blocked')


def exists(store):
    return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='session_model_choices'").fetchone())


def row(store,sid):
    return store.db.execute('SELECT * FROM session_model_choices WHERE session_id=?',(sid,)).fetchone() if exists(store) else None


def values(session):return {key:session.get(key,False if key=='fastMode' else None) for key in FIELDS}


def reference(saved):
    return {'revision':saved['revision'],'requestId':saved['request_id'],'afterRunId':saved['after_run_id']}


def public(store,sid):
    saved=row(store,sid)
    if saved is None:return {'selectionRevision':0,'selectionStateRevision':0,'pendingModel':None}
    pending=None
    if saved['state'] in OPEN:
        payload=json.loads(saved['payload'])
        pending={**reference(saved),'state':saved['state'],'choice':payload['choice'],
            'reason':saved['reason'],'updatedAt':saved['updated_at']}
    return {'selectionRevision':saved['revision'],'selectionStateRevision':saved['state_revision'],'pendingModel':pending}


def capture(store,sid,session,original=None,command=None):
    """Only model fields vary; settings revision, rights and original leases do not."""
    if original is not None:
        # The trusted frozen queue is checked byte-for-byte again by admission
        # and its original full-config credential lease. A model-only choice
        # must not retrospectively make that older input undeliverable.
        saved=row(store,sid)
        if saved is not None and original.get('revision')==session['revision'] and original.get('providerId')==session['providerId']:
            session={**session,**values(original)}
        return session,original.get('modelChoice')
    if command is not None:
        accepted=json.loads(command['payload']).get('_modelSelection')
        if accepted:return {**session,**accepted['choice']},accepted.get('modelChoice')
    saved=row(store,sid)
    if saved is not None and saved['state'] in OPEN:
        return {**session,**json.loads(saved['payload'])['choice']},reference(saved)
    return session,None


def qualification(store,sid,session,choice,providers):
    selected={**session,**choice}
    validate_settings(selected,providers)
    common=session['engine'].get('kind')=='studio'
    model=next((m for m in provider_models(providers,session['providerId'],direct=common) if m['id']==choice['model']),None)
    if not model or model.get('available') is False:
        raise ProjectFault('The selected next-run model is unavailable. Its choice was retained.',409)
    selection=None
    if common:
        from studio_selection import target,route_changed
        if route_changed(session['engine'],providers,session['providerId']):
            raise ProjectFault('The original connection route changed. Review Session settings before choosing a next-run model.',409)
        selection=target(store,sid,providers,selected)
        proof={k:selection.get(k) for k in ('apiProvider','apiModel','apiChat','apiZaiClient')}
        proof['route']=session['engine'].get('api')
    else:
        proof={'providerId':session['providerId'],'kind':session['engine'].get('kind','codex'),
            'model':{k:model.get(k) for k in ('id','efforts','fastModeAvailable','imageInputs','inputModalities','contextWindow')}}
        if session['engine'].get('kind')=='claude-code':
            from claude_provider_store import ClaudeProviders,account_identity
            from claude_history import ClaudeHistory
            provider=ClaudeProviders(providers).get(session['providerId'])
            history=ClaudeHistory(store,sid).get()
            if not history['accountIdentity'] or account_identity(provider['account'])!=history['accountIdentity']:
                raise ProjectFault('The original native Claude account changed. Keep this conversation and choose the new account in a new session.',409)
            proof['account']={'revision':provider['revision'],'runtimeProfileId':provider['runtimeProfileId'],
                'identity':history['accountIdentity'],'nativeSessionId':history['runtime']['nativeSessionId']}
    return hashlib.sha256(encode(proof).encode()).hexdigest(),selection,selected


def receipt(store,sid,rid):
    store.row(sid)
    saved=store.db.execute("SELECT response FROM requests WHERE request_id=? AND session_id=? AND kind='model_choice'",(identity(rid),sid)).fetchone()
    if not saved:raise ProjectFault('Original model-choice request not found.',404)
    return json.loads(saved['response'])['receipt']


class Choices:
    def __init__(self,store):self.store=store

    def schema(self):
        with self.store.db:self.store.db.execute('''CREATE TABLE IF NOT EXISTS session_model_choices(
            session_id TEXT PRIMARY KEY REFERENCES sessions(id),revision INTEGER NOT NULL,
            request_id TEXT NOT NULL,after_run_id TEXT NOT NULL REFERENCES runs(id),
            state TEXT NOT NULL,payload TEXT NOT NULL,reason TEXT,updated_at TEXT NOT NULL,
            state_revision INTEGER NOT NULL)''')

    @guarded
    def accept(self,sid,data,providers,unbound=False):
        required={'requestId','revision','selectionRevision','afterRunId',*FIELDS}
        if (not isinstance(data,dict) or set(data)!=required or type(data['revision']) is not int or data['revision']<1
                or type(data['selectionRevision']) is not int or data['selectionRevision']<0
                or type(data['fastMode']) is not bool or not isinstance(data['model'],str) or not isinstance(data['effort'],str)):
            raise ProjectFault('Invalid next-run model choice.',400)
        rid=identity(data['requestId']);after=identity(data['afterRunId']);sid=identity(sid)
        fingerprint=hashlib.sha256(encode({'sessionId':sid,**data}).encode()).hexdigest()
        self.schema();db=self.store.db;db.execute('BEGIN IMMEDIATE')
        try:
            previous=db.execute('SELECT * FROM requests WHERE request_id=?',(rid,)).fetchone()
            if previous:
                if previous['kind']!='model_choice' or previous['session_id']!=sid or previous['payload_hash']!=fingerprint:
                    raise ProjectFault('This request ID belongs to another original model choice.',409)
                return {'receipt':json.loads(previous['response'])['receipt'],'session':self.store.get(sid)}
            session=self.store.get(sid);current=row(self.store,sid)
            if unbound:raise ProjectFault('Reconcile the original unbound workers before choosing a next-run model.',503)
            if session['revision']!=data['revision'] or (current['revision'] if current else 0)!=data['selectionRevision']:
                raise ProjectFault('The session or next-run model choice changed. Reload before choosing again.',409)
            latest=session['latestRun']
            if latest is None or latest['id']!=after:
                raise ProjectFault('The original run boundary changed. Your current draft was preserved.',409)
            from goal_store import pending
            if pending(self.store):raise ProjectFault('Wait for the original Goal control before choosing a next-run model.',409)
            if db.execute("SELECT COUNT(*) FROM requests WHERE session_id=? AND kind='model_choice'",(sid,)).fetchone()[0]>=4096:
                raise ProjectFault('This session reached its model-choice history limit.',409)
            choice=values(data);baseline=values(session);state='cancelled' if choice==baseline else 'pending'
            proof=None if state=='cancelled' else qualification(self.store,sid,session,choice,providers)[0]
            payload={'choice':choice,'proof':proof,'settingsRevision':session['revision'],'providerId':session['providerId']}
            revision=(current['revision'] if current else 0)+1;stamp=now()
            original={'requestId':rid,'sessionId':sid,'selectionRevision':revision,'afterRunId':after,'state':state,'choice':choice,'acceptedAt':stamp}
            db.execute('INSERT INTO session_model_choices VALUES (?,?,?,?,?,?,NULL,?,?) ON CONFLICT(session_id) DO UPDATE SET revision=excluded.revision,request_id=excluded.request_id,after_run_id=excluded.after_run_id,state=excluded.state,payload=excluded.payload,reason=NULL,updated_at=excluded.updated_at,state_revision=excluded.state_revision',
                (sid,revision,rid,after,state,encode(payload),stamp,(current['state_revision'] if current else 0)+1))
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',(rid,'model_choice',fingerprint,sid,encode({'receipt':original,'intent':payload})))
            from quota_wait import control
            control(self.store,sid,'An accepted model choice permanently ended the previous quota wait.')
            from run_store import event
            event(self.store,sid,None,'modelChoice',public(self.store,sid),False)
            db.execute('UPDATE sessions SET updated_at=? WHERE id=?',(stamp,sid))
            db.commit();return {'receipt':original,'session':self.store.get(sid)}
        finally:
            if db.in_transaction:db.rollback()


def settings_guard(store,sid,data):
    saved=row(store,sid)
    if saved is None:return
    if any(key in data for key in ('providerId',*FIELDS)) and data.get('selectionRevision')!=saved['revision']:
        raise ProjectFault('The next-run model choice changed. Reload Session settings before saving.',409)
    if saved['state'] in OPEN:
        raise ProjectFault('Apply or cancel the original next-run model choice before changing other session settings.',409)


def changed_settings(store,sid):
    from quota_wait import control
    control(store,sid,'Accepted model or provider settings permanently ended the previous quota wait.')
    saved=row(store,sid)
    if saved is not None:
        store.db.execute("UPDATE session_model_choices SET revision=revision+1,state_revision=state_revision+1,state='cancelled',reason=NULL,updated_at=? WHERE session_id=?",(now(),sid))


def admission(store,sid,data,snapshot):
    marker=snapshot.get('modelChoice')
    if marker is None:return
    proof=getattr(store,'_model_choice_admission',None)
    if proof!={'sessionId':sid,'requestId':data['requestId'],'marker':marker,'choice':values(snapshot),'settingsRevision':snapshot['revision']}:
        raise ProjectFault('The original next-run model boundary needs confirmed coordinator admission. No run was started.',409)


async def prepare(host,store,sid,data,frozen=None):
    """Confirm the whole original run and context before a new run is admitted.

    Older frozen inputs bypass the newer choice; already accepted newer inputs
    keep their own original intent even after replacement or cancellation.
    """
    from run_store import get_run
    store._model_choice_admission=None
    session=store.get(sid);command=None
    if data.get('mode')=='goal':
        from goal_store import Goals
        command=Goals(store).command(sid,identity(data['goalRequestId']))
    selected,marker=capture(store,sid,session,frozen,command)
    if marker is None:return
    # Do not hold a SQLite writer across the asynchronous unit observation.
    unit_active=await host.active_unit(identity(marker['afterRunId']))
    db=store.db;db.execute('BEGIN IMMEDIATE')
    try:
        session=store.get(sid);selected,current_marker=capture(store,sid,session,frozen,command)
        if current_marker!=marker:raise ProjectFault('The next-run model choice changed during admission. Read its original receipt.',409)
        request=db.execute("SELECT response FROM requests WHERE request_id=? AND session_id=? AND kind='model_choice'",(marker['requestId'],sid)).fetchone()
        if request is None:raise ProjectFault('The original next-run model choice is unavailable.',409)
        original=json.loads(request['response']);intent=original['intent'];accepted=original['receipt']
        if marker!={'revision':accepted['selectionRevision'],'requestId':accepted['requestId'],'afterRunId':accepted['afterRunId']}:
            raise ProjectFault('The original next-run model boundary changed.',409)
        source=get_run(store,marker['afterRunId']);worker=json.loads(source['worker'] or '{}')
        if source['session_id']!=sid:raise ProjectFault('The original model choice belongs to another session.',403)
        if source['busy'] or source['state'] not in ('completed','failed','interrupted'):
            raise ProjectFault('The next-run model is waiting for the complete, confirmed original run to end.',409)
        if unit_active:raise ProjectFault('The original run service has not ended. The next-run choice was retained.',409)
        from model_operations import alive
        if worker.get('pid') and alive(worker['pid'],worker.get('birth')):
            raise ProjectFault('The original worker process has not ended. The next-run choice was retained.',409)
        source_config=json.loads(source['config'])
        if (worker and source_config['engine'].get('kind')=='studio' or worker.get('runEndProtocol')==1) and worker.get('processEnd',{}).get('confirmed') is not True:
            raise ProjectFault('The original model/worker process end is unconfirmed. The next-run choice was retained.',409)
        if store.db.execute("SELECT 1 FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND (t.state='unknown' OR t.result IS NULL) LIMIT 1",(sid,)).fetchone():
            raise ProjectFault('Resolve the original tool receipt before applying the next-run model.',409)
        if db.execute('SELECT 1 FROM runs WHERE busy=1 LIMIT 1').fetchone():
            raise ProjectFault('Another original run still owns this workspace. The next-run choice was retained.',409)
        if session['revision']!=intent['settingsRevision'] or session['providerId']!=intent['providerId']:
            raise ProjectFault('The original settings or connection changed. Choose the next-run model again.',409)
        choice=values(selected)
        if choice!=intent['choice']:raise ProjectFault('The queued model choice differs from its original accepted intent.',409)
        proof,selection,target=qualification(store,sid,session,choice,host.config['providers'])
        if proof!=intent['proof']:raise ProjectFault('The model facts or credential binding changed. Choose the next-run model again; the original input was retained.',409)
        if selection is not None:
            from studio_selection import records,validate_context
            validate_context(store,sid,records(store,sid),selection)
        from image_inputs import qualify,history
        from document_inputs import qualify as qualify_documents
        qualify_documents(store,sid,target,history(store,sid));qualify(store,sid,target,host.config['providers'],[])
        if source_config['engine'].get('kind')!='studio':
            if source_config['engine'].get('kind')=='claude-code':
                from claude_history import ClaudeHistory
                if ClaudeHistory(store,sid).get()['phase'] not in ('allocated','ready'):
                    raise ProjectFault('The original native Claude history is unconfirmed. The next-run choice was retained.',409)
            elif store.row(sid)['thread_id']:
                import sqlite3
                from native_tools import provider as native_provider
                try:native_provider(store,sid)
                except (OSError,ValueError,sqlite3.Error):
                    raise ProjectFault('The original native conversation metadata is unavailable or changed. The next-run choice was retained.',409) from None
            from generated_images import GeneratedImages
            if GeneratedImages(store,sid).rows():
                model=next((m for m in provider_models(host.config['providers'],session['providerId']) if m['id']==choice['model']),None)
                if not model or model.get('imageInputs')!='supported':
                    raise ProjectFault('The original generated-image context needs a qualified image model. The next-run choice was retained.',409)
        saved=row(store,sid)
        if saved and saved['request_id']==marker['requestId'] and saved['state'] in OPEN:
            # Model selection owns a revision separate from session rights.
            # Older accepted queues retain their exact settings revision.
            settings=json.loads(store.row(sid)['settings']);settings.update(choice)
            db.execute('UPDATE sessions SET settings=?,updated_at=? WHERE id=?',(encode(settings),now(),sid))
            db.execute("UPDATE session_model_choices SET state='applied',state_revision=state_revision+1,reason=NULL,updated_at=? WHERE session_id=?",(now(),sid))
            from run_store import event
            event(store,sid,None,'modelChoice',public(store,sid),False)
        db.commit()
        store._model_choice_admission={'sessionId':sid,'requestId':data['requestId'],'marker':marker,'choice':choice,'settingsRevision':session['revision']}
    except ProjectFault as error:
        saved=row(store,sid)
        if (saved and saved['request_id']==marker['requestId'] and saved['state'] in OPEN
                and (saved['state']!='blocked' or saved['reason']!=str(error))):
            db.execute("UPDATE session_model_choices SET state='blocked',state_revision=state_revision+1,reason=?,updated_at=? WHERE session_id=?",(str(error),now(),sid))
            from run_store import event
            event(store,sid,None,'modelChoice',public(store,sid),False)
            db.commit()
        raise
    finally:
        if db.in_transaction:db.rollback()
