"""Public, English data contract shared by browser and future agent adapters."""
import json
from storage import RoadmapFault


def common(row):
    return {'id': row['id'], 'notes': row['notes'], 'revision': row['revision'],
            'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def item(row):
    return {**common(row), 'subversionId': row['subversion_id'],
            'description': row['description'], 'status': row['status'], 'order': row['position']}


def snapshot(db):
    # Keep a coherent read transaction even when another session is editing.
    db.execute('BEGIN')
    try:
        for table in ('versions', 'subversions', 'tasks', 'acceptances'):
            if db.execute('SELECT count(*) FROM ' + table).fetchone()[0] > 10000:
                raise RoadmapFault('The roadmap is too large for a full snapshot. Use a bounded view.', 413)
        root = db.execute('SELECT * FROM roadmap WHERE singleton=1').fetchone()
        versions = []
        for version in db.execute('SELECT * FROM versions ORDER BY position,major,minor,id'):
            number = f'{version["major"]}.{version["minor"]}'
            children = []
            for sub in db.execute('SELECT * FROM subversions WHERE version_id=? ORDER BY position,patch,id', (version['id'],)):
                children.append({**common(sub), 'versionId': version['id'], 'number': f'{number}.{sub["patch"]}',
                                 'title': sub['title'], 'description': sub['description'],
                                 'status': sub['status'], 'order': sub['position'],
                                 'tasks': [item(x) for x in db.execute('SELECT * FROM tasks WHERE subversion_id=? ORDER BY position,id', (sub['id'],))],
                                 'acceptances': [item(x) for x in db.execute('SELECT * FROM acceptances WHERE subversion_id=? ORDER BY position,id', (sub['id'],))]})
            versions.append({**common(version), 'number': number + '.X', 'title': version['title'],
                             'vision': version['vision'], 'status': version['status'],
                             'order': version['position'], 'subversions': children})
        value = {**common(root), 'projectId': root['project_id'], 'description': root['description'],
                 'currentVersionId': root['current_version_id'], 'versions': versions}
        if len(json.dumps(value, ensure_ascii=False).encode()) > 1500000:
            raise RoadmapFault('The roadmap is too large for a full snapshot. Use a bounded view.', 413)
        return value
    finally:
        db.rollback()
