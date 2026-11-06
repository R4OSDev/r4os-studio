"""Revision-bound, project-bound pages for browser, tools and export traversal."""
import base64
import json
from model import common, item
from storage import RoadmapFault
from validation import fields, integer, target


def root_row(db):
    return db.execute('SELECT * FROM roadmap WHERE singleton=1').fetchone()


def binding(db):
    root = db.execute('SELECT revision,current_version_id FROM roadmap WHERE singleton=1').fetchone()
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


def page_aggregates(db, kind, rows):
    if kind not in ('version','subversion') or not rows:return None
    ids=[row['id'] for row in rows];slots=','.join('?' for _ in ids)
    values={ident:{table:{'open':0,'done':0,'discarded':0,'total':0} for table in ('tasks','acceptances')} for ident in ids}
    for table in ('tasks','acceptances'):
        totals="SUM(t.status='open'),SUM(t.status='done'),SUM(t.status='discarded'),COUNT(*)"
        if kind=='version':
            query='SELECT s.version_id,'+totals+' FROM '+table+' t JOIN subversions s ON s.id=t.subversion_id WHERE s.version_id IN ('+slots+') GROUP BY s.version_id'
        else:query='SELECT t.subversion_id,'+totals+' FROM '+table+' t WHERE t.subversion_id IN ('+slots+') GROUP BY t.subversion_id'
        for parent,opened,done,discarded,total in db.execute(query,ids):
            values[parent][table]={'open':opened,'done':done,'discarded':discarded,'total':total}
    counts={};parents={}
    if kind=='version':
        counts=dict(db.execute('SELECT version_id,COUNT(*) FROM subversions WHERE version_id IN ('+slots+') GROUP BY version_id',ids))
    else:
        version_ids=list({row['version_id'] for row in rows})
        parents={row['id']:row for row in db.execute('SELECT id,major,minor FROM versions WHERE id IN ('+','.join('?' for _ in version_ids)+')',version_ids)}
    return {'progress':values,'counts':counts,'parents':parents}


def entity(db, kind, row, aggregates=None):
    if kind == 'roadmap':
        return {**common(row), 'projectId': row['project_id'], 'description': row['description'],
                'currentVersionId': row['current_version_id'], 'progress': progress(db)}
    if kind == 'version':
        return {**common(row), 'number': f'{row["major"]}.{row["minor"]}.X',
                'title': row['title'], 'vision': row['vision'], 'status': row['status'], 'order': row['position'],
                'subversionCount': aggregates['counts'].get(row['id'],0) if aggregates is not None else db.execute('SELECT count(*) FROM subversions WHERE version_id=?', (row['id'],)).fetchone()[0],
                'progress': aggregates['progress'][row['id']] if aggregates is not None else progress(db, version_id=row['id'])}
    if kind == 'subversion':
        parent = aggregates['parents'][row['version_id']] if aggregates is not None else db.execute('SELECT major,minor FROM versions WHERE id=?', (row['version_id'],)).fetchone()
        return {**common(row), 'versionId': row['version_id'], 'number': f'{parent["major"]}.{parent["minor"]}.{row["patch"]}',
                'title': row['title'], 'description': row['description'], 'status': row['status'],
                'order': row['position'], 'progress': aggregates['progress'][row['id']] if aggregates is not None else progress(db, subversion_id=row['id'])}
    return item(row)


def page(db, project_id, request):
    fields(request, ['collection'], ['versionId', 'subversionId', 'cursor', 'limit'])
    collection = request['collection']
    definitions = {'versions': ('version', 'roadmap_id', None, 'position,major,minor,id'),
                   'subversions': ('subversion', 'version_id', request.get('versionId'), 'position,patch,id'),
                   'tasks': ('task', 'subversion_id', request.get('subversionId'), 'position,id'),
                   'acceptances': ('acceptance', 'subversion_id', request.get('subversionId'), 'position,id')}
    if not isinstance(collection, str) or collection not in definitions:
        raise RoadmapFault('Invalid roadmap collection.', 400)
    kind, parent_key, parent_id, ordering = definitions[collection]
    if collection=='versions':parent_id=db.execute('SELECT id FROM roadmap WHERE singleton=1').fetchone()[0]
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
    visible=rows[:limit];aggregates=page_aggregates(db,kind,visible)
    return {**bound, 'items': [entity(db, kind, row, aggregates) for row in visible], 'nextCursor': cursor}


def read(db, project_id, request):
    operation = request['operation']
    db.execute('BEGIN')
    try:
        if operation == 'revision':
            fields(request, ['operation', 'projectId'])
            return binding(db)
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
