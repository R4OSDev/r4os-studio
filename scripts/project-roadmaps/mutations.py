"""Short SQLite transactions with original-result receipts and explicit parents."""
import hashlib
import json
import sqlite3
import uuid
from reads import binding, entity, root_row
from storage import RoadmapFault, timestamp
from validation import KINDS, fields, identity, integer, number, target, text


def selected_input(value, allowed, require_description=False, context='Roadmap input'):
    fields(value, optional=allowed, context=context,
           hint='Task and acceptance text uses description; title is not supported.' if require_description else '')
    result = {}
    for key, val in value.items():
        if key == 'status':
            result[key] = val
        elif key == 'number':
            result[key] = val
        else:
            result[key] = text(val, 240 if key == 'title' else 32768,
                               required=key == 'title' or (key == 'description' and require_description))
    return result


def create(db, reference, data, now):
    target(db, reference, needs_id=False); kind = reference['kind']
    if kind == 'roadmap':
        raise RoadmapFault('This project already has its roadmap.', 409)
    allowed = ('number', 'title', 'vision', 'notes', 'status') if kind == 'version' else (
        ('number', 'title', 'description', 'notes', 'status') if kind == 'subversion' else ('description', 'notes', 'status'))
    value = selected_input(data, allowed, require_description=kind in ('task', 'acceptance'), context=kind + ' create input')
    required = 'title' if kind in ('version', 'subversion') else 'description'
    if required not in value:
        raise RoadmapFault(kind + ' create input requires ' + required + '.', 400)
    table = KINDS[kind]
    if db.execute('SELECT count(*) FROM ' + table).fetchone()[0] >= (1000 if kind == 'version' else 10000):
        raise RoadmapFault('This roadmap collection has reached its entry limit.', 413)
    parent_key, parent_id = ('roadmap_id', root_row(db)['id']) if kind == 'version' else (
        ('version_id', reference['versionId']) if kind == 'subversion' else ('subversion_id', reference['subversionId']))
    position = db.execute('SELECT coalesce(max(position),-1)+1 FROM ' + table + ' WHERE ' + parent_key + '=?', (parent_id,)).fetchone()[0]
    record = {'id': str(uuid.uuid4()), parent_key: parent_id, 'position': position,
              'created_at': now, 'updated_at': now, **{k: v for k, v in value.items() if k != 'number'}}
    if kind == 'version':
        current = db.execute('SELECT * FROM versions WHERE id=?', (root_row(db)['current_version_id'],)).fetchone()
        major, minor = number(value.get('number', f'{current["major"]}.{current["minor"] + 1}.X'))
        record.update(major=major, minor=minor)
    elif kind == 'subversion':
        parent = db.execute('SELECT * FROM versions WHERE id=?', (parent_id,)).fetchone()
        patch = db.execute('SELECT coalesce(max(patch),0)+1 FROM subversions WHERE version_id=?', (parent_id,)).fetchone()[0]
        record['patch'] = number(value.get('number', f'{parent["major"]}.{parent["minor"]}.{patch}'), parent)
    valid_status = ('open', 'complete', 'discarded') if kind in ('version', 'subversion') else ('open', 'done', 'discarded')
    if record.get('status', 'open') not in valid_status:
        raise RoadmapFault('Invalid status for this roadmap entry.', 400)
    keys = list(record)
    db.execute('INSERT INTO ' + table + '(' + ','.join(keys) + ') VALUES(' + ','.join('?' for _ in keys) + ')', list(record.values()))
    row = db.execute('SELECT * FROM ' + table + ' WHERE id=?', (record['id'],)).fetchone()
    return entity(db, kind, row)


def update(db, reference, data, now, action):
    row = target(db, reference); kind = reference['kind']; table = KINDS[kind]
    if action in ('append_notes', 'replace_notes'):
        fields(data, ['notes'])
        addition = text(data['notes'])
        notes = row['notes'] + ('\n' if row['notes'] and addition else '') + addition if action == 'append_notes' else addition
        value = {'notes': text(notes)}
    else:
        allowed = ('description', 'notes') if kind == 'roadmap' else (
            ('number', 'title', 'vision', 'notes', 'status') if kind == 'version' else (
                ('number', 'title', 'description', 'notes', 'status') if kind == 'subversion' else ('description', 'notes', 'status')))
        value = selected_input(data, allowed, require_description=kind in ('task', 'acceptance'), context=kind + ' update input')
        if not value:
            raise RoadmapFault('Select a field to change.', 400)
        if 'status' in value:
            valid = ('open', 'complete', 'discarded') if kind in ('version', 'subversion') else ('open', 'done', 'discarded')
            if value['status'] not in valid:
                raise RoadmapFault('Invalid status for this roadmap entry.', 400)
        if 'number' in value:
            raw = value.pop('number')
            if kind == 'version':
                value['major'], value['minor'] = number(raw)
            else:
                parent = db.execute('SELECT * FROM versions WHERE id=?', (row['version_id'],)).fetchone()
                value['patch'] = number(raw, parent)
    db.execute('UPDATE ' + table + ' SET ' + ','.join(k + '=?' for k in value)
               + (',revision=revision+1,updated_at=?' if kind != 'roadmap' else '') + ' WHERE id=?',
               [*value.values(), *([now] if kind != 'roadmap' else []), row['id']])
    return row['id']


def reorder(db, reference, data, now):
    target(db, reference, needs_id=False); kind = reference['kind']
    if kind == 'roadmap':
        raise RoadmapFault('There is only one roadmap in a project.', 400)
    fields(data, ['ids'])
    ids = data['ids']
    if not isinstance(ids, list) or len(ids) > 500:
        raise RoadmapFault('Select the complete ordered collection of at most 500 entries.', 400)
    for value in ids:
        identity(value)
    if len(set(ids)) != len(ids):
        raise RoadmapFault('Each entry must occur exactly once in the order.', 400)
    table = KINDS[kind]
    parent_key, parent_id = ('roadmap_id', root_row(db)['id']) if kind == 'version' else (
        ('version_id', reference['versionId']) if kind == 'subversion' else ('subversion_id', reference['subversionId']))
    actual = [row['id'] for row in db.execute('SELECT id FROM ' + table + ' WHERE ' + parent_key + '=?', (parent_id,))]
    if set(actual) != set(ids):
        raise RoadmapFault('The ordered collection changed. Reload before saving.', 409)
    db.executemany('UPDATE ' + table + ' SET position=?,revision=revision+1,updated_at=? WHERE id=?',
                   [(position, now, value) for position, value in enumerate(ids)])
    return {'kind': kind, 'ids': ids}


def mutate(db, project_id, body, initialize=False):
    if initialize:
        fields(body, ['requestId'])
    else:
        fields(body, ['requestId', 'expectedRevision', 'currentVersionId', 'target', 'action'], ['input'])
    identity(body['requestId'])
    if not initialize:
        integer(body['expectedRevision'], 1, 9007199254740991); identity(body['currentVersionId'])
    fingerprint = hashlib.sha256(json.dumps({'projectId': project_id, 'initialize': initialize, **body},
                                           sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    db.execute('PRAGMA max_page_count=' + str((64 * 1024 * 1024) // db.execute('PRAGMA page_size').fetchone()[0]))
    db.execute('BEGIN IMMEDIATE')
    try:
        receipt = db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?', (body['requestId'],)).fetchone()
        if receipt:
            if receipt['request_hash'] != fingerprint:
                raise RoadmapFault('This roadmap request ID was already used for different input.', 409)
            return json.loads(receipt['result'])
        root = root_row(db); now = timestamp()
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 50000:
            raise RoadmapFault('Roadmap receipt storage needs maintenance. Existing receipts were preserved.', 503)
        if initialize:
            result = {**binding(db), 'entity': entity(db, 'roadmap', root)}
        else:
            if body['expectedRevision'] != root['revision'] or body['currentVersionId'] != root['current_version_id']:
                raise RoadmapFault('The roadmap changed. Reload its current version and revision before saving.', 409)
            if db.execute("SELECT id FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted') LIMIT 1").fetchone():
                raise RoadmapFault('Reconcile the current roadmap workflow before editing.', 409)
            action, reference, data = body['action'], body['target'], body.get('input', {})
            if not isinstance(data, dict):
                raise RoadmapFault('Invalid roadmap input.', 400)
            if action not in ('create', 'update', 'append_notes', 'replace_notes', 'delete', 'reorder', 'set_current'):
                raise RoadmapFault('Unsupported roadmap mutation.', 400)
            target(db, reference, needs_id=action not in ('create', 'reorder'))
            if action == 'create':
                changed = create(db, reference, data, now)
            elif action in ('update', 'append_notes', 'replace_notes'):
                update(db, reference, data, now, action)
                changed = None
            elif action == 'delete':
                fields(data, ['confirm'])
                if data['confirm'] is not True or reference.get('kind') == 'roadmap':
                    raise RoadmapFault('Explicitly confirm removal of the selected roadmap entry.', 400)
                row = target(db, reference)
                if reference['kind'] == 'version' and row['id'] == root['current_version_id']:
                    raise RoadmapFault('Select another current version before removing this version.', 409)
                db.execute('DELETE FROM ' + KINDS[reference['kind']] + ' WHERE id=?', (row['id'],))
                changed = {'id': row['id'], 'kind': reference['kind'], 'deleted': True}
            elif action == 'reorder':
                changed = reorder(db, reference, data, now)
            elif action == 'set_current':
                fields(data)
                row = target(db, reference)
                if reference['kind'] != 'version':
                    raise RoadmapFault('Select a main version.', 400)
                db.execute('UPDATE roadmap SET current_version_id=?', (row['id'],))
                changed = entity(db, 'version', row)
            else:
                raise RoadmapFault('Unsupported roadmap mutation.', 400)
            db.execute('UPDATE roadmap SET revision=revision+1,updated_at=?', (now,))
            if changed is None:
                changed = entity(db, reference['kind'], target(db, reference))
            result = {**binding(db), 'entity': changed}
        db.execute('INSERT INTO receipts(request_id,request_hash,revision,result,created_at) VALUES(?,?,?,?,?)',
                   (body['requestId'], fingerprint, result['revision'], json.dumps(result, ensure_ascii=False), now))
        db.commit()
        return result
    except sqlite3.IntegrityError:
        raise RoadmapFault('The roadmap entry conflicts with its parent, number or status. Reload before saving.', 409) from None
    except sqlite3.OperationalError as error:
        if error.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise RoadmapFault('The roadmap is being edited. Reload before retrying.', 409) from None
        raise RoadmapFault('Roadmap storage is unavailable. Existing data was preserved.', 503) from None
    finally:
        db.rollback()
