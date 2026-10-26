"""Run admission, durable events and tool receipts shared by host and run workers."""
import hashlib
import json
import uuid
from session_store import encode, now, identity, validate_settings
from store import ProjectFault
from system_prompt import snapshot as prompt_snapshot
from project_agents import snapshot as project_snapshot


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
    raw = encode(value)
    if len(raw.encode()) > 262144: raise ProjectFault('Agent item exceeds the output limit.')
    store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                     (session_id, run_id, value['id'], raw))
    event(store, session_id, run_id, 'item', value, commit)


def get_run(store, run_id):
    row = store.db.execute('SELECT * FROM runs WHERE id=?', (identity(run_id),)).fetchone()
    if row is None: raise ProjectFault('Run not found.', 404)
    return row


def admit(store, session_id, data, provider_dir):
    if (set(data) - {'projectInstructions', 'skillSelection', 'skillScripts'} != {'requestId', 'revision', 'text'}
        or type(data['revision']) is not int or any(key in data and (type(data[key]) is not int or data[key] != 1) for key in ('projectInstructions', 'skillSelection', 'skillScripts'))
        or ('skillScripts' in data and data.get('skillSelection') != 1)):
        raise ProjectFault('Unexpected run fields.', 400)
    if not isinstance(data['text'], str) or not data['text'].strip() or len(data['text'].encode()) > 65536 or '\x00' in data['text']:
        raise ProjectFault('Enter a message of at most 64 KiB.', 400)
    key = identity(data['requestId']); request_hash = hashlib.sha256(encode({'sessionId': session_id,
        **{k: v for k, v in data.items() if k not in ('projectInstructions', 'skillSelection', 'skillScripts')}}).encode()).hexdigest()
    store.db.execute('BEGIN IMMEDIATE')
    try:
        previous = store.db.execute('SELECT * FROM runs WHERE request_id=?', (key,)).fetchone()
        if previous:
            if previous['payload_hash'] != request_hash: raise ProjectFault('This request ID belongs to another run submission.')
            return store.run_present(previous), False
        session = store.get(session_id)
        if session['revision'] != data['revision']: raise ProjectFault('Session settings changed. Reload before sending.')
        if store.db.execute('SELECT 1 FROM runs WHERE busy=1').fetchone():
            raise ProjectFault('Another run is using this workspace.')
        validate_settings(session, provider_dir)
        snapshot = {k: session[k] for k in ('providerId', 'model', 'effort', 'fastMode', 'permissions', 'engine', 'revision')}
        snapshot['owner'] = {'type': store.owner_type, 'id': store.owner_id}
        if data.get('skillSelection') == 1:
            from skill_application import freeze
            snapshot['skillAccess'] = freeze(store, session['skillOverrides'], terminal=data.get('skillScripts') == 1)
        if store.owner_type == 'skill':
            if 'projectInstructions' in data: raise ProjectFault('Project instructions do not apply to skill sessions.', 400)
            from skill_prompt import snapshot as skill_prompt_snapshot
            snapshot['skillManagerPrompt'] = skill_prompt_snapshot(store.projects)
        else:
            snapshot['projectPins'] = store.project['pins']
            snapshot['systemPrompt'] = prompt_snapshot(store.projects)
            snapshot['projectInstructions'] = project_snapshot(store.projects, store.project_id, store.project)
        ident = str(uuid.uuid4()); stamp = now()
        store.db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,?,NULL)',
                         (ident, session_id, key, request_hash, 'queued', 1, encode(snapshot), stamp))
        item(store, session_id, ident, {'id': 'user-' + key, 'runId': ident, 'type': 'user', 'text': data['text'], 'status': 'completed'}, False)
        unavailable = snapshot.get('skillAccess', {}).get('unavailable', [])
        if unavailable:
            item(store, session_id, ident, {'id': 'skill-notice-' + ident, 'runId': ident, 'type': 'notice', 'status': 'completed',
                'text': 'Enabled skills without a published revision were unavailable for this run: ' + ', '.join(v['name'] for v in unavailable)}, False)
        event(store, session_id, ident, 'run', store.run_present(get_run(store, ident)), False)
        store.db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (stamp, session_id))
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
