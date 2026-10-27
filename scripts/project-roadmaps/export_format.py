"""Deterministic UTF-8 archive of one complete version and project roadmap notes."""
from reads import root_row

VERSION_LABELS = {'open': 'Open', 'complete': 'Complete', 'discarded': 'Discarded'}
ITEM_LABELS = {'open': 'Open', 'done': 'Done', 'discarded': 'Discarded'}


def details(row):
    return (f'ID: {row["id"]}\nOrder: {row["position"]}\nRevision: {row["revision"]}\n'
            f'Created: {row["created_at"]}\nUpdated: {row["updated_at"]}\n')


def block(label, value):
    return f'\n{label}:\n{value}\n\n'


def archive_text(db, version):
    root = root_row(db)
    number = f'{version["major"]}.{version["minor"]}.X'
    yield '# R4OS Studio project roadmap\n\n'
    yield (f'Project ID: {root["project_id"]}\nRoadmap ID: {root["id"]}\n'
           f'Roadmap revision: {root["revision"]}\nCurrent version ID: {root["current_version_id"]}\n'
           f'Created: {root["created_at"]}\nUpdated: {root["updated_at"]}\n')
    yield block('Roadmap description', root['description'])
    yield block('Roadmap notes', root['notes'])
    yield f'## Version {number} — {version["title"]}\n\n'
    yield details(version)
    yield f'Status: {VERSION_LABELS[version["status"]]}\n'
    yield block('Vision', version['vision'])
    yield block('Version notes', version['notes'])
    yield '### Subversions\n\n'
    count = 0
    for sub in db.execute('SELECT * FROM subversions WHERE version_id=? ORDER BY position,patch,id', (version['id'],)):
        count += 1
        yield f'#### {version["major"]}.{version["minor"]}.{sub["patch"]} — {sub["title"]}\n\n'
        yield details(sub)
        yield f'Parent version ID: {sub["version_id"]}\nStatus: {VERSION_LABELS[sub["status"]]}\n'
        yield block('Description', sub['description'])
        yield block('Subversion notes', sub['notes'])
        for table, label in (('tasks', 'Tasks'), ('acceptances', 'Acceptance items')):
            yield f'##### {label}\n\n'
            items = 0
            for item in db.execute('SELECT * FROM ' + table + ' WHERE subversion_id=? ORDER BY position,id', (sub['id'],)):
                items += 1
                yield f'###### {label[:-1] if table == "tasks" else "Acceptance item"} {items}\n\n'
                yield details(item)
                yield f'Parent subversion ID: {item["subversion_id"]}\nStatus: {ITEM_LABELS[item["status"]]}\n'
                yield block('Description', item['description'])
                yield block('Notes', item['notes'])
            if not items:
                yield 'None.\n\n'
    if not count:
        yield 'None.\n\n'
    yield '# End of complete version archive\n'
