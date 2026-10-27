"""Project/version-scoped workflow history with stable keyset pages."""
import base64
import json

from cleanup import public
from reads import binding
from storage import RoadmapFault
from validation import fields, identity, integer, target


def read(db, project_id, request):
    if request['operation'] == 'workflow':
        fields(request, ['operation', 'projectId', 'workflowId'])
        return public(db, project_id, request['workflowId'])
    fields(request, ['operation', 'projectId'], ['versionId', 'cursor', 'limit'])
    limit = integer(request.get('limit', 5), 1, 20)
    version_id = request.get('versionId')
    db.execute('BEGIN')
    try:
        if version_id: target(db, {'kind': 'version', 'id': identity(version_id)})
        scope = {'projectId': project_id, 'versionId': version_id}
        where, parameters = ["kind='cleanup'"], []
        if version_id: where.append('version_id=?'); parameters.append(version_id)
        if 'cursor' in request:
            cursor = request['cursor']
            if not isinstance(cursor, str) or len(cursor) > 1024: raise RoadmapFault('Invalid workflow page cursor.', 400)
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                fields(decoded, [*scope, 'createdAt', 'id']); identity(decoded['id'])
                if not isinstance(decoded['createdAt'], str) or len(decoded['createdAt']) > 80: raise ValueError()
            except (ValueError, TypeError, UnicodeError): raise RoadmapFault('Invalid workflow page cursor.', 400) from None
            if {key: decoded[key] for key in scope} != scope: raise RoadmapFault('This workflow page belongs to another project or version.', 409)
            anchor = db.execute("SELECT created_at,version_id FROM workflows WHERE id=? AND kind='cleanup'", (decoded['id'],)).fetchone()
            if anchor is None or anchor['created_at'] != decoded['createdAt'] or (version_id and anchor['version_id'] != version_id):
                raise RoadmapFault('This workflow page anchor is no longer available.', 409)
            where.append('(created_at<? OR (created_at=? AND id<?))'); parameters.extend([decoded['createdAt'], decoded['createdAt'], decoded['id']])
        rows = db.execute('SELECT id,created_at FROM workflows WHERE ' + ' AND '.join(where) + ' ORDER BY created_at DESC,id DESC LIMIT ?', [*parameters, limit + 1]).fetchall()
        values = []
        for row in rows[:limit]:
            value = public(db, project_id, row['id'])
            value.pop('documents', None)
            summary = value.get('documentationSummary') or ''
            value['documentationSummary'] = summary[:512]; value['summaryTruncated'] = len(summary) > 512
            values.append(value)
        cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            cursor = base64.urlsafe_b64encode(json.dumps({**scope, 'createdAt': last['created_at'], 'id': last['id']}, separators=(',', ':')).encode()).decode().rstrip('=')
        return {**binding(db), 'items': values, 'nextCursor': cursor}
    finally: db.rollback()
