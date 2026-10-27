"""Revision-bound, project-bound pages for browser, tools and export traversal."""
import base64
import json
from model import common, item
from storage import RoadmapFault
from validation import fields, integer, target


def root_row(db):
    return db.execute('SELECT * FROM roadmap WHERE singleton=1').fetchone()


def binding(db):
    root = root_row(db)
    return {'revision': root['revision'], 'currentVersionId': root['current_version_id']}


def progress(db, version_id=None, subversion_id=None):
    result = {}
    for table in ('tasks', 'acceptances'):
        query = 'SELECT t.status,count(*) FROM ' + table + ' t JOIN subversions s ON s.id=t.subversion_id'
        args = []
        if subversion_id:
            query += ' WHERE s.id=?'; args = [subversion_id]
        elif version_id:
            query += ' WHERE s.version_id=?'; args = [version_id]
        counts = {'open': 0, 'done': 0, 'discarded': 0}
        counts.update(dict(db.execute(query + ' GROUP BY t.status', args)))
        result[table] = {**counts, 'total': sum(counts.values())}
    return result


def entity(db, kind, row):
    if kind == 'roadmap':
        return {**common(row), 'projectId': row['project_id'], 'description': row['description'],
                'currentVersionId': row['current_version_id'], 'progress': progress(db)}
    if kind == 'version':
        return {**common(row), 'number': f'{row["major"]}.{row["minor"]}.X',
                'title': row['title'], 'vision': row['vision'], 'status': row['status'], 'order': row['position'],
                'subversionCount': db.execute('SELECT count(*) FROM subversions WHERE version_id=?', (row['id'],)).fetchone()[0],
                'progress': progress(db, version_id=row['id'])}
    if kind == 'subversion':
        parent = db.execute('SELECT major,minor FROM versions WHERE id=?', (row['version_id'],)).fetchone()
        return {**common(row), 'versionId': row['version_id'], 'number': f'{parent["major"]}.{parent["minor"]}.{row["patch"]}',
                'title': row['title'], 'description': row['description'], 'status': row['status'],
                'order': row['position'], 'progress': progress(db, subversion_id=row['id'])}
    return item(row)


def page(db, project_id, request):
    fields(request, ['collection'], ['versionId', 'subversionId', 'cursor', 'limit'])
    collection = request['collection']
    definitions = {'versions': ('version', 'roadmap_id', root_row(db)['id'], 'position,major,minor,id'),
                   'subversions': ('subversion', 'version_id', request.get('versionId'), 'position,patch,id'),
                   'tasks': ('task', 'subversion_id', request.get('subversionId'), 'position,id'),
                   'acceptances': ('acceptance', 'subversion_id', request.get('subversionId'), 'position,id')}
    if not isinstance(collection, str) or collection not in definitions:
        raise RoadmapFault('Invalid roadmap collection.', 400)
    kind, parent_key, parent_id, ordering = definitions[collection]
    reference = {'kind': kind, **{k: request[k] for k in ('versionId', 'subversionId') if k in request}}
    target(db, reference, needs_id=False)
    limit = integer(request.get('limit', 10), 1, 20)
    bound = binding(db)
    scope = {'projectId': project_id, 'collection': collection, 'parentId': parent_id, 'revision': bound['revision']}
    offset = 0
    if request.get('cursor') is not None:
        cursor = request['cursor']
        if not isinstance(cursor, str) or len(cursor) > 1024:
            raise RoadmapFault('Invalid roadmap page cursor.', 400)
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
            fields(value, [*scope, 'offset'])
            offset = integer(value['offset'], 0, 100000)
        except (ValueError, TypeError, UnicodeError):
            raise RoadmapFault('Invalid roadmap page cursor.', 400) from None
        if {k: value[k] for k in scope} != scope:
            raise RoadmapFault('The roadmap page changed. Reload before continuing.', 409)
    rows = db.execute('SELECT * FROM ' + collection + ' WHERE ' + parent_key + '=? ORDER BY ' + ordering + ' LIMIT ? OFFSET ?',
                      (parent_id, limit + 1, offset)).fetchall()
    cursor = None
    if len(rows) > limit:
        cursor = base64.urlsafe_b64encode(json.dumps({**scope, 'offset': offset + limit}, separators=(',', ':')).encode()).decode().rstrip('=')
    return {**bound, 'items': [entity(db, kind, row) for row in rows[:limit]], 'nextCursor': cursor}


def read(db, project_id, request):
    operation = request['operation']
    db.execute('BEGIN')
    try:
        if operation == 'overview':
            fields(request, ['operation', 'projectId'], ['cursor', 'limit'])
            return {'exists': True, 'roadmap': entity(db, 'roadmap', root_row(db)),
                    'versions': page(db, project_id, {'collection': 'versions', **{k: request[k] for k in ('cursor', 'limit') if k in request}})}
        if operation == 'list':
            fields(request, ['operation', 'projectId', 'collection'], ['versionId', 'subversionId', 'cursor', 'limit'])
            return page(db, project_id, {k: v for k, v in request.items() if k not in ('operation', 'projectId')})
        if operation == 'current':
            fields(request, ['operation', 'projectId'])
            row = db.execute('SELECT * FROM versions WHERE id=?', (root_row(db)['current_version_id'],)).fetchone()
            return {**binding(db), 'entity': entity(db, 'version', row)}
        fields(request, ['operation', 'projectId', 'target'])
        reference = request['target']
        row = target(db, reference)
        if operation == 'notes':
            return {**binding(db), 'id': row['id'], 'notes': row['notes']}
        return {**binding(db), 'entity': entity(db, reference['kind'], row)}
    finally:
        db.rollback()
