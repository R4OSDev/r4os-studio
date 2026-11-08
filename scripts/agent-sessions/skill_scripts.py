"""Read-only frozen package bindings; execution remains an existing terminal call."""
from skill_application import Snapshot


def bindings(worker, snapshot=None):
    access = worker.config.get('skillAccess')
    if not access or access.get('terminal') is not True: return []
    if access.get('schema') != 1: raise ValueError('Unsupported skill script scope.')
    if not access['entries']: return []
    snapshot = snapshot or Snapshot(worker.store.projects)
    return [(entry['id'], snapshot.revision(entry, verify_files=True)[0]) for entry in access['entries']]
