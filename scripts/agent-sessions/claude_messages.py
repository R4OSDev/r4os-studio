"""Bound queued Claude inputs and actual SDK input-ID acknowledgements.

Capturing an intent authorizes no native process. Dispatch still needs the
original frozen selection, readable history, current lease/account and quota
admission. Host 'submitted' is not a native input receipt.
"""
import hashlib
import json

from attachment_store import birth
from claude_history import ClaudeHistory
from claude_provider_store import ClaudeProviders
from claude_run_leases import ClaudeRunLeases
from message_store import Messages, exists
from run_store import get_run, request_text, transition
from session_store import encode, now
from store import ProjectFault


def digest(value): return hashlib.sha256(encode(value).encode()).hexdigest()


def context(store, sid, providers):
    saved = ClaudeHistory(store, sid).get(); runtime = saved['runtime']
    provider = ClaudeProviders(providers).get(saved['providerId'])
    source = None
    if saved['phase'] in ('opening', 'active'):
        run = get_run(store, saved['activeRunId']); config = json.loads(run['config'])
        worker = json.loads(run['worker'] or '{}')
        original = {key: worker.get(key) for key in ('release', 'pid', 'birth')}
        if (run['session_id'] != sid or not run['busy'] or run['state'] not in ('starting', 'running')
                or config['engine'].get('claude') != runtime or config['providerId'] != saved['providerId']
                or type(original['pid']) is not int or original['pid'] < 1
                or not original['birth'] or birth(original['pid']) != original['birth'] or not original['release']):
            raise ProjectFault('The original Claude worker is stopping or unconfirmed. The queued input was not submitted.', 409)
        selected = config.get('claudeProvider')
        if not isinstance(selected, dict): raise ProjectFault('The original Claude account binding is unavailable.', 409)
        lease = {**selected, 'studioSessionId': sid, 'ownerType': store.owner_type, 'ownerId': store.owner_id,
                 'runId': run['id'], 'requestId': run['request_id'], 'nativeSessionId': runtime['nativeSessionId']}
        if not ClaudeRunLeases(providers).current_lease(lease, original):
            raise ProjectFault('The original Claude credential lease is no longer active. The queue was preserved.', 409)
        source = {'runId': run['id'], 'requestId': run['request_id'], 'configSha256': digest(config), 'worker': original}
    elif saved['phase'] not in ('allocated', 'ready'):
        raise ProjectFault('The original Claude history is unconfirmed. No queued inference was authorized.', 409)
    return {'schema': 1, 'nativeSessionId': runtime['nativeSessionId'], 'runtimeProfileId': runtime['runtimeProfileId'],
            'providerId': provider['id'], 'providerRevision': provider['revision'],
            'accountIdentity': saved['accountIdentity'], 'source': source}


def validate_queue(store, sid, frozen):
    config = frozen['config']
    if config['engine'].get('kind') != 'claude-code': return
    value = frozen.get('claudeQueue'); selected = config.get('claudeProvider', {})
    saved = ClaudeHistory(store, sid).get()
    expected = {'schema': 1, 'nativeSessionId': config['engine']['claude']['nativeSessionId'],
                'runtimeProfileId': selected.get('runtimeProfileId'), 'providerId': config['providerId'],
                'providerRevision': selected.get('providerRevision'), 'accountIdentity': selected.get('accountIdentity')}
    if (not isinstance(value, dict) or set(value) != {*expected, 'source'}
            or any(value.get(key) != val for key, val in expected.items())
            or saved['runtime'] != config['engine']['claude'] or saved['phase'] not in ('allocated', 'ready')):
        raise ProjectFault('The original Claude queue/history binding changed. Remove and submit the saved input explicitly.', 409)
    source = value['source']
    if source is not None:
        run = get_run(store, source['runId']); worker = json.loads(run['worker'] or '{}')
        if (run['session_id'] != sid or run['busy'] or run['state'] == 'unknown'
                or run['request_id'] != source['requestId'] or digest(json.loads(run['config'])) != source['configSha256']
                or {key: worker.get(key) for key in ('release', 'pid', 'birth')} != source['worker']):
            raise ProjectFault('The preceding original Claude run is unconfirmed or changed. The queue was held.', 409)


def queued(worker):
    if not exists(worker.store): return False
    return worker.store.db.execute("SELECT 1 FROM session_messages WHERE session_id=? AND request_id=? AND run_id=? AND mode='queue'",
        (worker.session_id, worker.row['request_id'], worker.run_id)).fetchone() is not None


def acknowledge(worker, frame):
    w = worker
    if not queued(w): return False
    reported = frame.get('identity', {}); ids = reported.get('nativeInputRequestIds', [])
    if reported.get('nativeType') not in ('assistant','stream_event','result','user'):
        return False  # Initialization/status tags do not acknowledge input.
    if not ids: return False
    if (ids != [w.row['request_id']] or reported.get('nativeSessionId') != w.config['engine']['claude']['nativeSessionId']
            or frame.get('native', {}).get('session_id') != reported.get('nativeSessionId')
            or frame.get('native', {}).get('type') != reported.get('nativeType')
            or reported.get('nativeType') not in ('assistant', 'stream_event', 'result', 'user')
            or not (reported.get('nativeMessageId') or reported.get('providerMessageId'))):
        raise ProjectFault('The native Claude input receipt belongs to another request. It was not replayed.', 409)
    messages = Messages(w.store); db = w.store.db
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS claude_input_receipts(
            request_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),run_id TEXT NOT NULL,
            payload TEXT NOT NULL,created_at TEXT NOT NULL)''')
    db.execute('BEGIN IMMEDIATE')
    try:
        row = messages.row(w.session_id, w.row['request_id']); run = get_run(w.store, w.run_id)
        frozen = json.loads(row['frozen']); data = json.loads(row['input'])
        if reported['nativeType']=='user' and (frame['native'].get('isReplay') is not True
                or reported.get('nativeInputReceiptKind')!='stdinEcho'
                or reported.get('nativeInputTextSha256')!=hashlib.sha256(data['text'].encode()).hexdigest()):
            raise ProjectFault('The native Claude echo does not match the original queued text.',409)
        meta = json.loads(run['worker'] or '{}')
        history = ClaudeHistory(w.store, w.session_id).get()
        if (row['state'] not in ('dispatching', 'accepted') or not run['busy'] or run['state'] not in ('starting', 'running', 'stopping')
                or row['run_id'] != w.run_id or frozen['config'] != w.config
                or history['phase'] not in ('opening', 'active') or history['activeRunId'] != w.run_id
                or data['text'] != request_text(w.store, w.run_id)
                or row['input_hash'] != digest({'sessionId': w.session_id, **data})
                or any(meta.get(k) != w.credential_worker[k] for k in ('release', 'pid', 'birth'))):
            raise ProjectFault('The original queued Claude request changed. Its input was not submitted again.', 409)
        binding = {'owner': {'type': w.store.owner_type, 'id': w.store.owner_id}, 'sessionId': w.session_id,
            'runId': w.run_id, 'requestId': row['request_id'], 'inputSha256': row['input_hash'],
            'configSha256': digest(w.config), 'nativeSessionId': reported['nativeSessionId'],
            'nativeInputRequestIds': ids, 'worker': w.credential_worker}
        previous = db.execute('SELECT payload FROM claude_input_receipts WHERE request_id=?', (row['request_id'],)).fetchone()
        if previous:
            if json.loads(previous[0])['binding'] != binding:
                raise ProjectFault('The original native input receipt conflicts. Its evidence was preserved.', 409)
        else:
            if row['state'] != 'dispatching': raise ProjectFault('Accepted Claude input has no original native receipt.', 409)
            payload = {'schema': 1, 'binding': binding, 'nativeMessageId': reported.get('nativeMessageId'),
                'providerMessageId': reported.get('providerMessageId'), 'nativeTurnId': None, 'nativeType': reported['nativeType'],
                'nativeInputReceiptKind': reported.get('nativeInputReceiptKind','responseEcho'),
                'nativeInputTextSha256':reported.get('nativeInputTextSha256')}
            db.execute('INSERT INTO claude_input_receipts VALUES (?,?,?,?,?)',
                (row['request_id'], w.session_id, w.run_id, encode(payload), now()))
        messages.finish(w.session_id, row['request_id'], 'accepted')
    finally:
        if db.in_transaction: db.rollback()
    w.sent = True
    w.input_receipt.set()
    if not w.stopping: transition(w.store, w.run_id, 'running')
    return True


def finalize(worker):
    if not queued(worker) or worker.input_receipt.is_set() or not worker.sent: return
    worker.uncertain_effect = True; worker.outcome = 'unknown'
    worker.error = worker.error or 'Native Claude did not confirm the original queued input ID. Inspect the retained request; it was not submitted again.'
    Messages(worker.store).finish(worker.session_id, worker.row['request_id'], 'unknown', worker.error)
