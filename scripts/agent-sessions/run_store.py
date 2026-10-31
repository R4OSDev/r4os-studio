from skill_lifecycle import guarded
"""Run admission, durable events and tool receipts shared by host and run workers."""
import hashlib
import json
import uuid
from session_store import encode, now, identity, validate_settings
from store import ProjectFault
from system_prompt import snapshot as prompt_snapshot
from project_agents import snapshot as project_snapshot

CAPABILITIES=('projectInstructions','skillSelection','skillScripts','nativeWebSearch','roadmapSettings','remoteHostTools','nativeImageInputs','documentInputs','imageGenerationSettings','liveGoalPreparation','environmentNotesSettings')


def fingerprint(session_id,data,attachments=()):
    value={k:v for k,v in data.items() if k not in CAPABILITIES}
    if 'attachments' in value:
        if value['attachments']!=[m['id'] for m in attachments]:raise ProjectFault('This request ID belongs to another attachment selection.',409)
        value['attachments']=list(attachments)
    return hashlib.sha256(encode({'sessionId':session_id,**value}).encode()).hexdigest()

def event(store, session_id, run_id, kind, payload, commit=True):
    raw = encode(payload)
    if len(raw.encode()) > 262144: raise ProjectFault('Agent event exceeds the output limit.')
    # Hard bounds preserve old data instead of silently truncating native history.
    total = store.db.execute('SELECT COALESCE(SUM(length(payload)),0) FROM events WHERE session_id=?', (session_id,)).fetchone()[0]
    terminal = (kind == 'run' and payload.get('state') in ('completed', 'failed', 'interrupted', 'unknown')) or kind == 'itemStatus'
    if total + len(raw) > 96 * 1024 * 1024 and not terminal: raise ProjectFault('Session history reached its storage limit.')
    cursor = store.db.execute('INSERT INTO events(session_id,run_id,kind,payload,created_at) VALUES (?,?,?,?,?)',
                              (session_id, run_id, kind, raw, now())).lastrowid
    if commit: store.db.commit()
    return cursor


def item(store, session_id, run_id, value, commit=True):
    run = get_run(store, run_id)
    if run['turn_id'] and json.loads(run['config']).get('goalExecution'):
        value.setdefault('turnId', run['turn_id'])
    raw = encode(value)
    if len(raw.encode()) > 262144: raise ProjectFault('Agent item exceeds the output limit.')
    store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                     (session_id, run_id, value['id'], raw))
    event(store, session_id, run_id, 'item', value, commit)


def get_run(store, run_id):
    row = store.db.execute('SELECT * FROM runs WHERE id=?', (identity(run_id),)).fetchone()
    if row is None: raise ProjectFault('Run not found.', 404)
    return row


def capture_input(store, session_id, data, provider_dir, image_capability=None, goal_command=None, saved_attachments=None, queued_claude=None, original=None):
    """Freeze a complete accepted selection without admitting a concurrent run."""
    session = store.get(session_id)
    goal_mode = data.get('mode') == 'goal'
    command = goal_command
    captured_goal = json.loads(command['payload'])['_goal'] if command else None
    validate_settings(session, provider_dir)
    from image_inputs import selected,qualify,history,reference
    attachments = saved_attachments if saved_attachments is not None else (selected(store,session_id,data.get('attachments',[])) if not goal_mode and 'attachments' in data else [])
    if saved_attachments:
        from image_inputs import file_path
        for metadata in saved_attachments: file_path(store, session_id, metadata)
    if attachments and data.get('nativeImageInputs')!=1:raise ProjectFault('This request needs qualified native image support.',503)
    if any(m['mode']!='localImage' for m in attachments) and data.get('documentInputs')!=1:
        raise ProjectFault('This request needs qualified document input support.',503)
    from document_inputs import qualify as document_qualify
    document_qualify(store,session_id,session,attachments)
    modalities=qualify(store,session_id,session,provider_dir,attachments)
    request_hash=fingerprint(session_id,data,attachments)
    snapshot = {k: session[k] for k in ('providerId', 'model', 'effort', 'fastMode', 'permissions', 'engine', 'revision')}
    # This affects the immutable API lease hash, so freeze it before reserve.
    snapshot['contextProtocol'] = 1
    snapshot['inputContractVersion']=1
    from environment_note_tools import availability
    snapshot['environmentNotesEnabled']=bool(data.get('environmentNotesSettings')==1 and session.get('environmentNotesEnabled',True) and availability(session['engine'].get('profile'))['available'])
    if 'liveGoalPreparation' in data:
        from profile import CODEX_VERSION, CODEX_SHA256
        snapshot['nativeGoalPreparation'] = data['liveGoalPreparation']==1 and session['engine'].get('version')==CODEX_VERSION and session['engine'].get('sha256')==CODEX_SHA256
        if not goal_mode and session['engine'].get('kind')=='claude-code':
            snapshot['claudeGoalPreparation']=data['liveGoalPreparation']==1
    if 'attachments' in data:snapshot['attachments']=attachments
    accepted=attachments+history(store,session_id)
    from attachment_files import freeze as freeze_attachment_files
    freeze_attachment_files(snapshot, accepted, original)
    if any(m['mode']=='localImage' for m in accepted):snapshot.update(imageContext=True,imageInputModalities=modalities)
    if any(m['mode'] in ('text','pdfText') for m in accepted):snapshot['documentContext']=True
    if goal_mode and session['engine'].get('kind') == 'claude-code':
        from claude_goal import freeze as freeze_claude_goal
        snapshot['claudeGoalExecution'] = freeze_claude_goal(store, session_id, command)
    elif goal_mode:
        snapshot['goalExecution'] = {'requestId': data['goalRequestId'], 'objective': captured_goal['objective'],
            'threadId':captured_goal['threadId'],'commandFingerprint':command['fingerprint'],
            'captureSha256':hashlib.sha256(encode(captured_goal).encode()).hexdigest()}
        from goal_recovery import snapshot as recovery_snapshot
        recovery=recovery_snapshot(store,session_id)
        if recovery:snapshot['goalRecovery']=recovery
    snapshot['webSearchEnabled'] = session['webSearchEnabled'] if data.get('nativeWebSearch') == 1 else False
    from image_generation import freeze as freeze_image_capability
    snapshot['imageGenerationEnabled']=session.get('imageGenerationEnabled',True)
    snapshot['imageGenerationCapability']=freeze_image_capability(session,image_capability)
    snapshot['nativeImageGeneration']=bool(data.get('imageGenerationSettings')==1 and snapshot['imageGenerationEnabled'] and snapshot['imageGenerationCapability']['available'])
    from generated_images import GeneratedImages
    generated_history=bool(GeneratedImages(store,session_id).rows())
    if snapshot['nativeImageGeneration'] or generated_history:
        from session_store import provider_models
        selected_model=next((v for v in provider_models(provider_dir,session['providerId']) if v['id']==session['model']),None)
        if not selected_model or selected_model.get('imageInputs')!='supported':
            raise ProjectFault('This conversation has generated-image context or requests image generation. Select an image-capable model; its history was preserved.',409)
        snapshot['imageInputModalities']=selected_model['inputModalities']
    snapshot['owner'] = {'type': store.owner_type, 'id': store.owner_id}
    snapshot['roadmapEnabled'] = store.owner_type == 'project' and session.get('roadmapEnabled', True)
    if data.get('skillSelection') == 1:
        from skill_application import freeze
        snapshot['skillAccess'] = freeze(store, session['skillOverrides'], terminal=data.get('skillScripts') == 1)
    if store.owner_type == 'skill':
        if 'projectInstructions' in data: raise ProjectFault('Project instructions do not apply to skill sessions.', 400)
        from skill_prompt import snapshot as skill_prompt_snapshot
        snapshot['skillManagerPrompt'] = skill_prompt_snapshot(store.projects)
    else:
        snapshot['projectPins'] = store.project['pins']
        # Trusted private metadata only; the terminal/Workspace cannot supply a
        # destination. Missing context stays explicit and cannot grant Push.
        from tool_defaults import repository_binding
        snapshot['githubBinding'] = repository_binding(store)
        from remote_context import snapshot as remote_snapshot
        snapshot.update(remote_snapshot(store, session['engine']['profile'], data.get('remoteHostTools') == 1))
        snapshot['systemPrompt'] = prompt_snapshot(store.projects)
        snapshot['projectInstructions'] = project_snapshot(store.projects, store.project_id, store.project)
    from api_models import freeze as freeze_api
    freeze_api(store,session_id,data,provider_dir,snapshot)
    from claude_selection import freeze as freeze_claude
    freeze_claude(store,session_id,data,provider_dir,snapshot,queue_context=queued_claude)
    from retry_protocol import freeze as freeze_retry
    freeze_retry(snapshot)
    return snapshot, attachments, request_hash


@guarded
def admit(store, session_id, data, provider_dir, image_capability=None, frozen=None):
    goal_mode = data.get('mode') == 'goal'
    expected = {'requestId', 'revision', 'mode', 'goalRequestId'} if goal_mode else {'requestId', 'revision', 'text'} | ({'attachments'} if 'attachments' in data else set())
    if (set(data) - set(CAPABILITIES) != expected
        or type(data['revision']) is not int or any(key in data and (type(data[key]) is not int or data[key] != 1) for key in CAPABILITIES)
        or (('roadmapSettings' in data or 'remoteHostTools' in data) and store.owner_type != 'project')
        or ('skillScripts' in data and data.get('skillSelection') != 1)):
        raise ProjectFault('Unexpected run fields.', 400)
    if not goal_mode and (not isinstance(data['text'], str) or (not data['text'].strip() and not data.get('attachments'))
            or any(0xd800<=ord(c)<=0xdfff for c in data['text']) or len(data['text'].encode()) > 65536 or '\x00' in data['text']):
        raise ProjectFault('Enter a message of at most64 KiB or select Ready attachments.', 400)
    key = identity(data['requestId'])
    store.db.execute('BEGIN IMMEDIATE')
    try:
        previous = store.db.execute('SELECT * FROM runs WHERE request_id=?', (key,)).fetchone()
        if previous:
            request_hash=fingerprint(session_id,data,json.loads(previous['config']).get('attachments',[]))
            if previous['payload_hash'] != request_hash: raise ProjectFault('This request ID belongs to another run submission.')
            return store.run_present(previous), False
        session = store.get(session_id)
        if session['revision'] != data['revision']: raise ProjectFault('Session settings changed. Reload before sending.')
        if frozen is None and not goal_mode:
            from message_store import pending_queue
            if pending_queue(store, session_id): raise ProjectFault('Continue or remove the existing message queue before starting another run.',409)
        if store.db.execute('SELECT 1 FROM runs WHERE busy=1').fetchone():
            raise ProjectFault('Another run is using this workspace.')
        from goal_store import Goals, pending
        if goal_mode:
            command = Goals(store).command(session_id, identity(data['goalRequestId']))
            snapshot = Goals(store).snapshot(session_id)
            goal_intent = json.loads(command['payload'])
            captured_goal = goal_intent.get('_goal')
            if (command['state'] != 'pending' or goal_intent['action'] != 'play' or not snapshot['goal'] or not captured_goal
                    or goal_intent.get('sessionRevision') != session['revision']
                    or any(snapshot['goal'].get(key) != captured_goal.get(key) for key in ('threadId','objective','createdAt','status'))):
                raise ProjectFault('This run has no accepted Goal Play command.', 409)
        elif pending(store) or Goals(store).snapshot(session_id)['phase']=='unknown':
            raise ProjectFault('Reconcile the original Goal control before sending a message.', 409)
        if store.owner_type == 'project':
            from project_maintenance import pending_git
            if pending_git(store.projects, store.project_id): raise ProjectFault('Reconcile the original Git pull before starting another agent run.', 409)
        snapshot, attachments, request_hash = capture_input(store, session_id, data, provider_dir, image_capability, command if goal_mode else None, frozen.get('attachments') if frozen else None, original=frozen)
        if frozen is not None:
            # Adding a capability to new captures must not upgrade old queued
            # inputs or change their already reserved API lease hash.
            from retry_protocol import freeze as freeze_retry
            freeze_retry(snapshot,original=frozen)
            if snapshot != frozen: raise ProjectFault('The queued selection changed. The queue was held; review its original input.',409)
            snapshot = frozen
        ident = snapshot.get('apiRunId') or snapshot.get('claudeRunId') or str(uuid.uuid4()); stamp = now()
        store.db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,?,NULL)',
                         (ident, session_id, key, request_hash, 'queued', 1, encode(snapshot), stamp))
        from image_inputs import reference
        reference(store,session_id,ident,attachments)
        if frozen is not None:
            store.db.execute("UPDATE session_messages SET state='dispatching',run_id=?,updated_at=? WHERE request_id=? AND session_id=? AND state='queued'", (ident, stamp, key, session_id))
            store.db.execute('UPDATE session_inboxes SET revision=revision+1 WHERE session_id=?',(session_id,))
        else:
            from message_store import exists as inbox_exists
            if not goal_mode and inbox_exists(store):
                # A new explicit ordinary send authorizes its own chain. Empty
                # holds from an earlier Stop must not disable future input.
                store.db.execute('UPDATE session_inboxes SET held=0,reason=NULL,revision=revision+1 WHERE session_id=?',(session_id,))
        if not goal_mode:
            item(store, session_id, ident, {'id': 'user-' + key, 'runId': ident, 'type': 'user', 'text': data['text'], 'status': 'completed',
                **({'attachments':attachments} if attachments else {})}, False)
        unavailable = snapshot.get('skillAccess', {}).get('unavailable', [])
        if unavailable:
            item(store, session_id, ident, {'id': 'skill-notice-' + ident, 'runId': ident, 'type': 'notice', 'status': 'completed',
                'text': 'Enabled skills without a published revision were unavailable for this run: ' + ', '.join(v['name'] for v in unavailable)}, False)
        event(store, session_id, ident, 'run', store.run_present(get_run(store, ident)), False)
        store.db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (stamp, session_id))
        if snapshot.get('apiProvider'):
            from api_provider_store import ApiProviders
            ApiProviders(provider_dir).reserve(ident,store.owner_type,store.owner_id,session_id,key,snapshot)
        if snapshot.get('claudeProvider'):
            from claude_selection import reserve as reserve_claude
            reserve_claude(store,session_id,ident,key,provider_dir,snapshot)
        store.db.commit()
        return store.run_present(get_run(store, ident)), True
    finally:
        if store.db.in_transaction: store.db.rollback()


def transition(store, run_id, state, error=None, turn_id=None, worker=None):
    store.db.execute('BEGIN IMMEDIATE')
    try:
        return _transition(store, run_id, state, error, turn_id, worker)
    finally:
        if store.db.in_transaction: store.db.rollback()


def _transition(store, run_id, state, error=None, turn_id=None, worker=None):
    row = get_run(store, run_id)
    if not row['busy']: return store.run_present(row)
    terminal = state in ('completed', 'failed', 'interrupted', 'unknown')
    # An accepted stop cannot be undone by a delayed native turn/start response.
    if row['state'] == 'stopping' and state in ('starting', 'running'): return store.run_present(row)
    with store.db:
        store.db.execute('UPDATE runs SET state=?,busy=?,error=?,turn_id=COALESCE(?,turn_id),worker=COALESCE(?,worker),completed_at=? WHERE id=?',
                         (state, 0 if terminal else 1, error, turn_id, encode(worker) if worker else None, now() if terminal else None, run_id))
        value = store.run_present(get_run(store, run_id))
        event(store, row['session_id'], run_id, 'run', value, False)
        if terminal and error:
            notice = {'id': 'run-result-' + run_id, 'runId': run_id, 'type': 'notice', 'text': error, 'status': state}
            store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                             (row['session_id'], run_id, notice['id'], encode(notice)))
        store.db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (now(), row['session_id']))
        from message_store import observe_run
        observe_run(store, row['session_id'], run_id, state, turn_id)
    return value


def events(store, session_id, after=0):
    store.row(session_id)
    if type(after) is not int or not 0 <= after <= 9007199254740991: raise ProjectFault('Invalid event cursor.', 400)
    rows = store.db.execute('SELECT * FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT 100', (session_id, after)).fetchall()
    batch = []; size = 0
    for r in rows:
        size += len(r['payload'].encode())
        if batch and size > 524288: break
        batch.append({'seq': r['seq'], 'runId': r['run_id'], 'kind': r['kind'], 'payload': json.loads(r['payload'])})
    return {'events': batch, 'session': store.get(session_id)}


def request_text(store, run_id):
    row = store.db.execute("SELECT payload FROM items WHERE run_id=? AND item_id LIKE 'user-%' LIMIT 1", (run_id,)).fetchone()
    if row is None: raise ProjectFault('Run input is unavailable.')
    return json.loads(row['payload'])['text']
