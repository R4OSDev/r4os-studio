"""Project navigation metadata in the shared project catalog."""
import re

from store import ProjectFault


def inventory(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_groups'").fetchone():
        return {'groups': [], 'memberships': {}}
    return {
        'groups': [dict(row) for row in db.execute('SELECT id,name,revision FROM project_groups')],
        'memberships': dict(db.execute('SELECT project_id,group_id FROM project_group_members')),
    }


def group_name(value):
    if isinstance(value, str):
        value = value.strip()
        if 1 <= len(value) <= 120 and not re.search(r'[\x00-\x1f\x7f\ud800-\udfff]', value):
            return value
    raise ProjectFault('Enter a group name with at most 120 characters.', 400)


def identity(value, nullable=False):
    if nullable and value is None:
        return value
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise ProjectFault('Invalid project or group ID.', 400)
    return value


def move_project(db, project_id, group_id, previous_group_id):
    if not db.execute("""SELECT 1 FROM projects WHERE id=? AND state='ready'
                      AND NOT EXISTS(SELECT 1 FROM project_deletions WHERE project_id=?)""", (project_id, project_id)).fetchone():
        raise ProjectFault('The project is unavailable.', 404)
    if group_id and not db.execute('SELECT 1 FROM project_groups WHERE id=?', (group_id,)).fetchone():
        raise ProjectFault('The destination group was deleted. Reload Projects before moving again.', 404)
    row = db.execute('SELECT group_id FROM project_group_members WHERE project_id=?', (project_id,)).fetchone()
    current = row[0] if row else None
    if current == group_id:
        return
    if current != previous_group_id:
        raise ProjectFault('The project was moved elsewhere. Reload Projects before moving again.')
    if group_id is None:
        db.execute('DELETE FROM project_group_members WHERE project_id=?', (project_id,))
    else:
        db.execute('''INSERT INTO project_group_members(project_id,group_id) VALUES (?,?)
                   ON CONFLICT(project_id) DO UPDATE SET group_id=excluded.group_id''', (project_id, group_id))


def mutate(db, request):
    action = request['operation']
    fields = {
        'create_group': {'name'}, 'rename_group': {'name', 'revision'}, 'delete_group': {'revision'},
        'move_project': {'groupId', 'previousGroupId'},
    }
    data = request.get('input')
    if not isinstance(data, dict) or data.keys() != fields[action]:
        raise ProjectFault('Invalid project group request.', 400)
    ident = identity(request.get('id'))
    name = group_name(data['name']) if 'name' in data else None
    revision = data.get('revision')
    if 'revision' in data and (type(revision) is not int or not 1 <= revision <= 9007199254740991):
        raise ProjectFault('Invalid group revision.', 400)
    db.execute('BEGIN IMMEDIATE')
    db.execute('''CREATE TABLE IF NOT EXISTS project_groups (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS project_group_members (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        group_id TEXT NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS project_group_members_group ON project_group_members(group_id)')
    if action == 'move_project':
        move_project(db, ident, identity(data['groupId'], nullable=True), identity(data['previousGroupId'], nullable=True))
        return inventory(db)
    group = db.execute('SELECT name,revision FROM project_groups WHERE id=?', (ident,)).fetchone()
    if action == 'create_group':
        if group is None:
            db.execute('INSERT INTO project_groups(id,name) VALUES (?,?)', (ident, name))
        elif group['name'] != name:
            raise ProjectFault('A group with this ID already exists.')
    elif group is None and action == 'rename_group':
        raise ProjectFault('The group was deleted.', 404)
    elif group is not None and not (action == 'rename_group' and group['name'] == name):
        if group['revision'] != revision:
            raise ProjectFault('The group changed. Reopen it before editing.')
        if action == 'rename_group':
            db.execute('UPDATE project_groups SET name=?,revision=revision+1 WHERE id=?', (name, ident))
        else:
            db.execute('DELETE FROM project_groups WHERE id=?', (ident,))
    return inventory(db)
