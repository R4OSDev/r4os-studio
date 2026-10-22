"""Unconfirmed guest effects keep their VM closed to new development jobs."""
import json
from pathlib import Path
from contracts import DevelopmentFault, identity
from jobs import folder, now
from layout import save


def path(projects, vm_id):
    return folder(Path(projects) / '.studio/development/Unconfirmed') / (identity(vm_id) + '.json')


def admission(projects, vm_id, state):
    file = path(projects, vm_id)
    if not file.exists(): return
    if file.resolve(strict=True) != file: raise DevelopmentFault('Invalid guest recovery record.', 503)
    value = json.loads(file.read_text())
    if state == 'stopped':
        save(folder(file.parent / 'Resolved') / (identity(value['jobId']) + '.json'),
            {**value, 'resolvedAt': now(), 'resolution': 'VM confirmed stopped; no guest action replayed'})
        file.unlink(); return
    raise DevelopmentFault('A previous execution has no confirmed cleanup receipt. Reconcile it or explicitly stop the assigned VM before another development job.')


def claim(projects, vm_id, value):
    file = path(projects, vm_id)
    if file.exists(): raise DevelopmentFault('A previous guest execution still requires recovery.')
    save(file, {'schema': 1, **value, 'createdAt': now()})


def release(projects, vm_id, job_id):
    file = path(projects, vm_id)
    if file.exists() and json.loads(file.read_text())['jobId'] == job_id: file.unlink()


def resolve(projects, vm_id, job_id, source):
    file = path(projects, vm_id)
    if not file.exists(): return
    if file.resolve(strict=True) != file: raise DevelopmentFault('Invalid guest recovery record.', 503)
    value = json.loads(file.read_text())
    if value['jobId'] != job_id: return
    save(folder(file.parent / 'Resolved') / (identity(job_id) + '.json'),
        {**value, 'resolvedAt': now(), 'resolution': source, 'replayed': False})
    file.unlink()
