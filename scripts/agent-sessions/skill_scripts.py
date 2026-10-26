"""Read-only frozen package bindings; execution remains an existing terminal call."""
from skill_application import revision


def bindings(worker):
    access = worker.config.get('skillAccess')
    if not access or access.get('terminal') is not True: return []
    if access.get('schema') != 1: raise ValueError('Unsupported skill script scope.')
    return [(entry['id'], revision(worker.store.projects, entry, verify_files=True)[0]) for entry in access['entries']]
