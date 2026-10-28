#!/usr/bin/env python3
"""Fixed host sidecar. Model arguments never select projects, paths or SQL."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'projects'))
from store import ProjectFault
from cli import operation
from storage import connection
from validation import fields, identity, integer


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def regular(path):
    info = path.lstat()
    if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProjectFault('The Roadmap run binding is unavailable.', 403)
    return info


@contextmanager
def authorize(projects, project_id, session_id, run_id, descriptor, release, tool, call_id, arguments):
    """Verify the actual parent process, original tool intent and inherited lease."""
    for value in (project_id, session_id, run_id): identity(value)
    path = projects / '.studio' / ('workspace-' + project_id + '.lock')
    info, held = regular(path), os.fstat(descriptor)
    if (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino):
        raise ProjectFault('The inherited Roadmap workspace lease belongs to another project.', 403)
    try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError): raise ProjectFault('The original workspace lease is unavailable.', 403) from None
    database = projects / project_id / 'Sessions/Sessions.sqlite'; regular(database)
    # Serialize short domain mutations with Stop admission. Never reacquire the
    # workspace lock independently of the inherited open file description.
    short_mutation = tool == 'update_roadmap' and arguments.get('operation') in ('initialize', 'mutate')
    db = sqlite3.connect(database.as_uri() + ('?mode=rw' if short_mutation else '?mode=ro'), uri=True, timeout=3)
    try:
        if short_mutation: db.execute('BEGIN IMMEDIATE')
        row = db.execute('''SELECT r.state,r.busy,r.config,r.worker,s.revision,t.tool,t.arguments_hash
            FROM runs r JOIN sessions s ON s.id=r.session_id JOIN tools t ON t.run_id=r.id
            WHERE r.id=? AND s.id=? AND s.project_id=? AND t.call_id=?''',
                         (run_id, session_id, project_id, call_id)).fetchone()
        if not row or row[0] not in ('starting', 'running') or row[1] != 1:
            raise ProjectFault('The Roadmap run is no longer accepting calls.', 403)
        config, worker = json.loads(row[2]), json.loads(row[3] or '{}')
        parent = os.getppid(); birth = (Path('/proc') / str(parent) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        fingerprint = hashlib.sha256(encode({'tool': 'studio_' + tool, 'arguments': arguments}).encode()).hexdigest()
        if (config.get('owner') != {'type': 'project', 'id': project_id}
                or config.get('roadmapEnabled') is not True or config.get('engine', {}).get('profile') not in ('studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11','studio-tools-v12')
                or config.get('revision') != row[4] or worker.get('pid') != parent or worker.get('birth') != birth
                or worker.get('release') != release or row[5] != 'studio_' + tool or row[6] != fingerprint):
            raise ProjectFault('Roadmap permission, profile, worker or original call binding changed.', 403)
        def contexts():
            from human_context import contexts as human_contexts
            yield from human_contexts(db,session_id,run_id,{'type':'project','id':project_id})

        def verify_origin(origin):
            fields(origin, ['runId', 'sessionId', 'sha256']); identity(origin['runId']); identity(origin['sessionId'])
            from human_context import text as human_text
            return human_text(db,origin['sessionId'],origin['runId'],{'type':'project','id':project_id})
        yield {'config': config, 'sessionId': session_id, 'runId': run_id, 'contexts': contexts, 'verify_origin': verify_origin}
    finally:
        db.rollback(); db.close()


def text_page(value, offset, limit):
    raw = value.encode('utf-8'); integer(offset, 0, len(raw)); integer(limit, 4, 8192)
    try: raw[:offset].decode('utf-8')
    except UnicodeError: raise ProjectFault('Use a returned UTF-8 byte offset.', 400) from None
    end = min(offset + limit, len(raw))
    while True:
        try: text = raw[offset:end].decode('utf-8'); break
        except UnicodeError: end -= 1
    return {'text': text, 'offset': offset, 'nextOffset': end if end < len(raw) else None,
            'byteLength': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'encoding': 'utf-8'}


def compact(value):
    if isinstance(value, list): return [compact(v) for v in value]
    if not isinstance(value, dict): return value
    result, texts = {}, {}
    for key, item in value.items():
        if key in ('notes', 'vision', 'description') and isinstance(item, str):
            preview = text_page(item, 0, 256)
            texts[key] = {'preview': preview['text'], 'byteLength': preview['byteLength'],
                          'sha256': preview['sha256'], 'previewTruncated': preview['nextOffset'] is not None}
        else: result[key] = compact(item)
    if texts: result['textFields'] = texts
    return result


def read(projects, project_id, arguments):
    view = arguments['view']; extra = {k: v for k, v in arguments.items() if k != 'view'}
    common = {'projectId': project_id}
    if view in ('overview', 'current', 'revision'):
        fields(extra, optional=('cursor', 'limit') if view == 'overview' else (),
               context='read_roadmap view=' + view,
               hint='expectedRevision is allowed only for view=text. This view returns the latest revision.')
        return compact(operation(projects, {'operation': view, **common, **extra}))
    if view in ('versions', 'subversions', 'tasks', 'acceptances'):
        return compact(operation(projects, {'operation': 'list', 'collection': view, **common, **extra}))
    if view == 'entry':
        fields(extra, ['target'])
        return compact(operation(projects, {'operation': 'get', **common, **extra}))
    if view == 'text':
        fields(extra, ['target', 'field'], ['offset', 'byteLimit', 'expectedRevision'])
        value = operation(projects, {'operation': 'get', **common, 'target': extra['target']})
        if 'expectedRevision' in extra and extra['expectedRevision'] != value['revision']:
            raise ProjectFault('The Roadmap text changed. Read the current revision before continuing.', 409)
        text = value['entity'].get(extra['field'])
        if not isinstance(text, str): raise ProjectFault('This Roadmap entry has no selected text field.', 400)
        return {**{k: value[k] for k in ('revision', 'currentVersionId')}, 'id': value['entity']['id'],
                'field': extra['field'], **text_page(text, extra.get('offset', 0), extra.get('byteLimit', 8192))}
    if view == 'receipt':
        fields(extra, ['requestId']); identity(extra['requestId'])
        with connection(projects, project_id) as db:
            if db is None: raise ProjectFault('Roadmap not initialized.', 404)
            row = db.execute('SELECT revision,result FROM receipts WHERE request_id=?', (extra['requestId'],)).fetchone()
            if row is None: raise ProjectFault('No confirmed Roadmap receipt exists for this request ID. Inspect before retrying.', 404)
            return {'requestId': extra['requestId'], 'revision': row['revision'], 'confirmed': True, 'result': compact(json.loads(row['result']))}
    if view == 'export_info':
        fields(extra, ['exportId'])
        return operation(projects, {'operation': view, **common, **extra})
    if view == 'export_chunk':
        fields(extra, ['exportId'], ['offset', 'byteLimit'])
        return operation(projects, {'operation': view, **common, 'exportId': extra['exportId'],
                                    'offset': extra.get('offset', 0), 'limit': extra.get('byteLimit', 8192)})
    raise ProjectFault('Unsupported Roadmap read view.', 400)


def call(projects, project_id, tool, arguments, actor=None):
    if tool == 'read_roadmap': return read(projects, project_id, arguments)
    if tool == 'cleanup_roadmap':
        from cleanup import call as cleanup_call
        with connection(projects, project_id) as db:
            if db is None: raise ProjectFault('Initialize this project roadmap before cleanup.', 404)
            return cleanup_call(db, projects, project_id, arguments, actor)
    op = arguments['operation']; data = {k: v for k, v in arguments.items() if k != 'operation'}
    if op == 'initialize':
        fields(data, ['requestId'])
        return compact(operation(projects, {'operation': 'initialize', 'projectId': project_id, **data}))
    if op == 'export':
        fields(data, ['requestId', 'versionId', 'expectedRevision', 'currentVersionId'])
    elif op != 'mutate': raise ProjectFault('Unsupported Roadmap update.', 400)
    return compact(operation(projects, {'operation': op, 'projectId': project_id, 'input': data}))


def main():
    os.umask(0o077)
    if len(sys.argv) != 7: raise ProjectFault('Invalid Roadmap sidecar invocation.', 400)
    projects, project_id, session_id, run_id = Path(sys.argv[1]).absolute(), sys.argv[2], sys.argv[3], sys.argv[4]
    descriptor, release = int(sys.argv[5]), sys.argv[6]
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072: raise ProjectFault('Roadmap arguments exceeded their limit.', 413)
    request = json.loads(raw); fields(request, ['tool', 'callId', 'arguments'])
    if not isinstance(request['callId'], str) or not 1 <= len(request['callId'].encode()) <= 256:
        raise ProjectFault('Invalid Roadmap call identity.', 400)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent-sessions'))
    from tool_catalog import validate_arguments
    if request['tool'] not in ('read_roadmap', 'update_roadmap', 'cleanup_roadmap'):
        raise ProjectFault('Unsupported Roadmap tool.', 400)
    validate_arguments(request['tool'], request['arguments'], 'studio-tools-v8')
    bound = {'tool': request['tool'], 'call_id': request['callId'], 'arguments': request['arguments']}
    with authorize(projects, project_id, session_id, run_id, descriptor, release, **bound) as actor:
        def check():
            with authorize(projects, project_id, session_id, run_id, descriptor, release, **bound) as fresh:
                if fresh['config'] != actor['config']:
                    raise ProjectFault('The frozen Roadmap run configuration changed.', 403)
        actor['check'] = check
        result = call(projects, project_id, request['tool'], request['arguments'], actor)
    rendered = encode({'result': result})
    if len(rendered.encode()) > 120000:
        raise ProjectFault('Roadmap result exceeds the tool limit. Read a smaller page or individual text field.', 413)
    print(rendered)


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(encode({'error': str(error), 'code': error.code})); sys.exit(1)
    except ValueError:
        print(encode({'error': 'Invalid Roadmap tool contract.', 'code': 400})); sys.exit(1)
    except Exception:
        print(encode({'error': 'The Roadmap result is unconfirmed. Inspect the original request receipt before retrying.', 'code': 503})); sys.exit(1)
