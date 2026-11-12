"""Unconfirmed guest effects keep their VM closed to new development jobs."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
from contracts import DevelopmentFault, identity
from jobs import folder, now
from layout import save


def path(projects, vm_id):
    return folder(Path(projects) / '.studio/development/Unconfirmed') / (identity(vm_id) + '.json')


@contextmanager
def locked(file):
    lock = folder(file.parent / 'locks') / file.name
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read(file):
    if not file.exists() and not file.is_symlink(): return None
    if file.resolve(strict=True) != file: raise DevelopmentFault('Invalid guest recovery record.', 503)
    return json.loads(file.read_text())


def archive(file, value, resolution, **proof):
    save(folder(file.parent / 'Resolved') / (identity(value['jobId']) + '.json'),
        {**value, 'resolvedAt': now(), 'resolution': resolution, 'replayed': False, **proof})
    file.unlink()


def admission(projects, vm_id, state):
    file = path(projects, vm_id)
    if not file.exists() and not file.is_symlink(): return
    with locked(file):
        value = read(file)
        if value is None: return
        if state == 'stopped':
            archive(file, value, 'VM confirmed stopped; no guest action replayed')
            return
        raise DevelopmentFault('A previous execution has no confirmed cleanup receipt. Reconcile it or explicitly stop the assigned VM before another development job.')


def claim(projects, vm_id, value):
    file = path(projects, vm_id)
    with locked(file):
        if read(file) is not None: raise DevelopmentFault('A previous guest execution still requires recovery.')
        save(file, {'schema': 1, **value, 'createdAt': now()})


def release(projects, vm_id, job_id):
    file = path(projects, vm_id)
    if not file.exists() and not file.is_symlink(): return
    with locked(file):
        value = read(file)
        if value is not None and value['jobId'] == job_id: file.unlink()


def resolve(projects, vm_id, job_id, source):
    file = path(projects, vm_id)
    if not file.exists() and not file.is_symlink(): return
    with locked(file):
        value = read(file)
        if value is not None and value['jobId'] == job_id: archive(file, value, source)


def resolve_after_boot(projects, boot):
    proof = boot.get('transition') or {}
    if not boot.get('connected') or proof.get('kind') not in ('qmp_reset', 'new_instance'): return
    file = path(projects, boot['vmId'])
    if not file.exists() and not file.is_symlink(): return
    with locked(file):
        value = read(file)
        if value is None: return
        target = value.get('target') or {}
        if (not target.get('bootId') or target['bootId'] in (proof.get('bootId'), boot['bootId'])
                or any(target.get(k) != boot[k] for k in ('vmId', 'vmRevision', 'imageId', 'imageSha256'))
                or (value.get('effectStartedAt') or value['createdAt']) >= proof.get('resetAt', proof['observedAt'])): return
        archive(file, value, 'Original VM boot ended; guest outcome remains unconfirmed', bootTransition=proof)
