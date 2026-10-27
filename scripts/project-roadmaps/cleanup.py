"""Journalled archive/document preparation. Version completion is a later phase."""
import hashlib
import json
import re
import uuid

from cleanup_files import archive, baseline, document, document_parts, root as workspace_root, temporary_name
from exports import open_archive, prepare as prepare_export
from reads import binding, root_row
from storage import RoadmapFault, timestamp
from validation import fields, identity, integer, text

TRIGGER = re.compile(r'\b(?:clean\s+up\s+(?:(?:the|this|our)\s+)?roadmap|tidy\s+up\s+(?:(?:the|this|our)\s+)?roadmap|roadmap\s+(?:bitte\s+)?aufräumen|räum(?:e|en)?\s+(?:bitte\s+)?(?:(?:die|diese|unsere)\s+)?roadmap\s+auf)\b', re.I)
TERMINAL = ('complete', 'cancelled', 'aborted')


def encoded(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(project_id, arguments):
    return hashlib.sha256(encoded({'operation': 'cleanup', 'projectId': project_id, **arguments}).encode()).hexdigest()


def get(db, project_id, workflow_id):
    identity(workflow_id)
    row = db.execute("SELECT * FROM workflows WHERE id=? AND kind='cleanup'", (workflow_id,)).fetchone()
    if row is None: raise RoadmapFault('Cleanup workflow not found in this project.', 404)
    payload = json.loads(row['payload'])
    if payload.get('schema') != 1 or payload.get('projectId') != project_id:
        raise RoadmapFault('Cleanup workflow needs maintenance. All files and history were preserved.', 503)
    return row, payload


def public(db, project_id, workflow_id):
    row, payload = get(db, project_id, workflow_id)
    return {'workflowId': row['id'], 'phase': row['phase'], 'versionId': row['version_id'],
            'number': payload['number'], 'revision': payload['revision'],
            'currentVersionId': payload['currentVersionId'],
            'archive': ({k: v for k, v in payload['archive'].items() if k in ('path', 'sha256', 'byteLength', 'exportId', 'encoding')}
                        if 'archive' in payload else None),
            'documents': payload.get('documents', []), 'documentCount': len(payload.get('documents', [])),
            'documentationSummary': payload.get('documentationSummary'),
            'baselineFileCount': len(payload['baseline']),
            'attemptCount': len(payload.get('attempts', [])),
            'capabilities': {'prepare': True, 'status': True, 'cancel': True, 'finalize': False},
            'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def current(db, payload):
    bound = binding(db)
    if bound['revision'] != payload['revision'] or bound['currentVersionId'] != payload['currentVersionId']:
        raise RoadmapFault('The original cleanup version or revision changed. Preserve files and reconcile it.', 409)


def update(db, workflow_id, payload, phase):
    db.execute('UPDATE workflows SET phase=?,payload=?,updated_at=? WHERE id=?',
               (phase, encoded(payload), timestamp(), workflow_id))


def receipt(db, request_id, hash_value, result):
    if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 50000:
        raise RoadmapFault('Roadmap receipt storage needs maintenance.', 503)
    db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',
               (request_id, hash_value, result['revision'], encoded(result), timestamp()))


def original(db, request_id, hash_value):
    row = db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?', (request_id,)).fetchone()
    if row:
        if row['request_hash'] != hash_value: raise RoadmapFault('This cleanup request ID has different original input.', 409)
        return json.loads(row['result'])
    return None


def file_rights(actor):
    if not all(actor['config'].get('permissions', {}).get('studio.' + key) is True for key in ('read_file', 'write_file', 'create_directory')):
        raise RoadmapFault('Cleanup preparation needs this run’s Read file, Write file and Create directory permissions.', 403)


def ready_work(db, version_id):
    if db.execute("SELECT 1 FROM subversions WHERE version_id=? AND status='open' LIMIT 1", (version_id,)).fetchone():
        raise RoadmapFault('Resolve open subversions before preparing cleanup; no status was changed.', 409)
    for table in ('tasks', 'acceptances'):
        if db.execute('SELECT 1 FROM ' + table + " t JOIN subversions s ON s.id=t.subversion_id WHERE s.version_id=? AND s.status!='discarded' AND t.status='open' LIMIT 1", (version_id,)).fetchone():
            raise RoadmapFault('Resolve open tasks and acceptance items before cleanup; nothing was marked done.', 409)
        if db.execute('SELECT 1 FROM ' + table + " t JOIN subversions s ON s.id=t.subversion_id WHERE s.version_id=? AND t.status='discarded' AND trim(t.notes)='' LIMIT 1", (version_id,)).fetchone():
            raise RoadmapFault('Record reasons in discarded item notes before cleanup.', 409)
    if db.execute("SELECT 1 FROM subversions WHERE version_id=? AND status='discarded' AND trim(notes)='' LIMIT 1", (version_id,)).fetchone():
        raise RoadmapFault('Record reasons in discarded subversion notes before cleanup.', 409)


def authorize_context(db, actor, version_id):
    # The caller attests actual cleanup intent. Link it to a real user request
    # in this session, including a still-pending request from an earlier run.
    consumed = {json.loads(row['payload']).get('origin', {}).get('runId')
                for row in db.execute("SELECT version_id,phase,payload FROM workflows WHERE kind='cleanup'")
                if row['phase'] != 'cancelled' or row['version_id'] != version_id}
    for candidate in actor['contexts']:
        if candidate['runId'] not in consumed and TRIGGER.search(candidate['text']):
            return {'runId': candidate['runId'], 'sessionId': actor['sessionId'],
                    'sha256': hashlib.sha256(candidate['text'].encode()).hexdigest()}
    raise RoadmapFault('Cleanup needs an explicit user cleanup request in this session. Ordinary roadmap implementation is not cleanup.', 403)


def prepare(db, projects, project_id, args, actor):
    fields(args, ['action', 'requestId', 'versionId', 'expectedRevision', 'currentVersionId', 'cleanupRequested'],
           ['workflowId', 'documents', 'documentationSummary'])
    if args['cleanupRequested'] is not True: raise RoadmapFault('Only an explicitly requested cleanup can be prepared.', 403)
    file_rights(actor)
    request_id = identity(args['requestId']); version_id = identity(args['versionId']); identity(args['currentVersionId'])
    integer(args['expectedRevision'], 1, 9007199254740991)
    request_hash = fingerprint(project_id, args)
    old = original(db, request_id, request_hash)
    if old is not None: return old
    if 'workflowId' in args:
        return confirm_documents(db, projects, project_id, args, actor, request_hash)
    if 'documents' in args or 'documentationSummary' in args: raise RoadmapFault('Prepare the archive workflow before confirming documentation.', 400)
    workflow_id = request_id
    existing = db.execute('SELECT id FROM workflows WHERE id=?', (workflow_id,)).fetchone()
    if existing:
        row, payload = get(db, project_id, workflow_id)
        if payload.get('requestHash') != request_hash: raise RoadmapFault('This workflow ID belongs to different original input.', 409)
        if row['phase'] in TERMINAL: raise RoadmapFault('This workflow is already closed. Read its original status.', 409)
    else:
        actor['check']()
        if binding(db) != {'revision': args['expectedRevision'], 'currentVersionId': args['currentVersionId']} or version_id != args['currentVersionId']:
            raise RoadmapFault('Cleanup must bind the current main version and its exact revision.', 409)
        # Read every baseline file while the caller retains its original
        # workspace lease and serializes terminal/file tools in this run.
        with workspace_root(projects, project_id) as (root_fd, workspace):
            before = baseline(root_fd)
        actor['check']()
        db.execute('BEGIN IMMEDIATE')
        try:
            if binding(db) != {'revision': args['expectedRevision'], 'currentVersionId': args['currentVersionId']} or version_id != args['currentVersionId']:
                raise RoadmapFault('Cleanup must bind the current main version and its exact revision.', 409)
            if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted') LIMIT 1").fetchone():
                raise RoadmapFault('Reconcile the existing cleanup workflow first.', 409)
            version = db.execute('SELECT * FROM versions WHERE id=?', (version_id,)).fetchone()
            if version is None or version['status'] == 'discarded': raise RoadmapFault('Select the current non-discarded main version.', 409)
            ready_work(db, version_id)
            if db.execute('SELECT count(*) FROM workflows').fetchone()[0] >= 1000: raise RoadmapFault('Cleanup workflow storage needs maintenance.', 503)
            origin = authorize_context(db, actor, version_id)
            payload = {'schema': 1, 'projectId': project_id, 'versionId': version_id,
                       'currentVersionId': version_id, 'revision': args['expectedRevision'],
                       'number': f'{version["major"]}.{version["minor"]}.X', 'workspace': workspace,
                       'baseline': before, 'origin': origin, 'requestHash': request_hash, 'attempts': []}
            stamp = timestamp()
            db.execute('INSERT INTO workflows VALUES(?,?,?,?,?,?,?)',
                       (workflow_id, 'cleanup', version_id, 'preparing', encoded(payload), stamp, stamp))
            db.commit()
        finally: db.rollback()
    current(db, payload); actor['check']()
    export_id = str(uuid.uuid5(uuid.UUID(workflow_id), 'complete-archive'))
    exported = prepare_export(db, projects, project_id, {'requestId': export_id, 'versionId': version_id,
        'expectedRevision': payload['revision'], 'currentVersionId': payload['currentVersionId']})
    if len(payload['attempts']) >= 8: raise RoadmapFault('Cleanup reached its archive attempt limit. Preserve staging files and reconcile the workflow.', 409)
    temporary = temporary_name(workflow_id); payload['attempts'].append(temporary)
    with db:
        db.execute('BEGIN IMMEDIATE'); current(db, payload); update(db, workflow_id, payload, 'archiving')
    actor['check']()
    with workspace_root(projects, project_id, payload['workspace']) as (root_fd, _):
        with open_archive(projects, project_id, export_id) as (info, stream):
            saved = archive(root_fd, stream, info, temporary, actor['check'])
    payload['archive'] = {**saved, 'exportId': exported['id'], 'encoding': 'utf-8'}
    with db:
        db.execute('BEGIN IMMEDIATE'); current(db, payload)
        update(db, workflow_id, payload, 'archive_ready')
        result = public(db, project_id, workflow_id)
        receipt(db, request_id, request_hash, result)
    return result


def confirm_documents(db, projects, project_id, args, actor, request_hash):
    fields(args, ['action', 'requestId', 'workflowId', 'versionId', 'expectedRevision', 'currentVersionId', 'cleanupRequested', 'documents', 'documentationSummary'])
    workflow_id = identity(args['workflowId']); row, payload = get(db, project_id, workflow_id)
    if row['phase'] not in ('archive_ready', 'documents_verified'): raise RoadmapFault('Verify the original archive before confirming knowledge documents.', 409)
    current(db, payload)
    if (args['versionId'], args['expectedRevision'], args['currentVersionId']) != (payload['versionId'], payload['revision'], payload['currentVersionId']):
        raise RoadmapFault('The documentation checkpoint belongs to another cleanup snapshot.', 409)
    documents = args['documents']
    if not isinstance(documents, list) or len(documents) > 32: raise RoadmapFault('Select at most 32 knowledge documents.', 400)
    summary = text(args['documentationSummary'], 8192, required=True)
    verified, seen = [], set()
    actor['check']()
    with workspace_root(projects, project_id, payload['workspace']) as (root_fd, _):
        # Confirm the complete original archive again, without rewriting it.
        exported = payload['archive']
        with open_archive(projects, project_id, exported['exportId']) as (info, stream):
            archive(root_fd, stream, info, temporary_name(workflow_id), actor['check'], create=False)
        for entry in documents:
            actor['check']()
            fields(entry, ['path', 'sha256', 'expectedSha256'])
            if not isinstance(entry['path'], str) or entry['path'] in seen: raise RoadmapFault('Each knowledge document must be selected once.', 400)
            seen.add(entry['path'])
            for value in (entry['sha256'], entry['expectedSha256']):
                if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)):
                    raise RoadmapFault('Use exact SHA-256 document receipts.', 400)
            if entry['sha256'] is None: raise RoadmapFault('A final document hash is required.', 400)
            before = payload['baseline'].get(entry['path'])
            if entry['expectedSha256'] != (before['sha256'] if before else None):
                raise RoadmapFault('A document original hash differs from the cleanup baseline. Preserve changes and reconcile.', 409)
            after = document(root_fd, entry['path'])
            if after['sha256'] != entry['sha256']: raise RoadmapFault('A knowledge document changed before its checkpoint.', 409)
            verified.append({**entry, 'byteLength': after['byteLength']})
    payload['documents'], payload['documentationSummary'] = verified, summary
    actor['check']()
    with db:
        db.execute('BEGIN IMMEDIATE'); current(db, payload); update(db, workflow_id, payload, 'documents_verified')
        result = public(db, project_id, workflow_id); receipt(db, args['requestId'], request_hash, result)
    return result


def call(db, projects, project_id, args, actor):
    action = args.get('action')
    if action != 'status':
        db.execute('PRAGMA max_page_count=' + str((64 * 1024 * 1024) // db.execute('PRAGMA page_size').fetchone()[0]))
    if action == 'prepare': return prepare(db, projects, project_id, args, actor)
    if action == 'status':
        fields(args, ['action', 'workflowId'], ['documents'])
        result = public(db, project_id, args['workflowId'])
        selected = args.get('documents', [])
        if not isinstance(selected, list) or len(selected) > 8:
            raise RoadmapFault('Inspect at most eight document receipt paths per status call.', 400)
        _, payload = get(db, project_id, args['workflowId'])
        result['documentStatus'] = []
        for entry in selected:
            fields(entry, ['path', 'sha256', 'expectedSha256']); document_parts(entry['path'])
            before = payload['baseline'].get(entry['path']); recorded = next((d for d in payload.get('documents', []) if d['path'] == entry['path']), None)
            result['documentStatus'].append({'path': entry['path'], 'baselineSha256': before['sha256'] if before else None,
                                            'recordedSha256': recorded['sha256'] if recorded else None,
                                            'reportedHashMatchesReceipt': recorded is not None and recorded['sha256'] == entry['sha256']})
        return result
    if action == 'cancel':
        fields(args, ['action', 'workflowId', 'requestId']); identity(args['requestId'])
        request_hash = fingerprint(project_id, args); old = original(db, args['requestId'], request_hash)
        if old is not None: return old
        row, payload = get(db, project_id, args['workflowId'])
        if row['phase'] == 'complete': raise RoadmapFault('A completed cleanup cannot be cancelled.', 409)
        actor['check']()
        with db:
            db.execute('BEGIN IMMEDIATE'); update(db, row['id'], payload, 'cancelled')
            result = public(db, project_id, row['id']); receipt(db, args['requestId'], request_hash, result)
        return result
    if action == 'finalize':
        return {'available': False, 'capability': 'cleanup_finalize',
                'message': 'Finalization is not enabled in this release. The main version and next version were not changed.'}
    raise RoadmapFault('Unsupported cleanup phase.', 400)
