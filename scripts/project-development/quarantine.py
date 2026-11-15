"""Unconfirmed guest effects keep their VM closed to new development jobs."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
from contracts import DevelopmentFault, identity
from jobs import folder, now
from layout import save
from development_units import LIFECYCLE_KINDS


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


def recovery_fault(value, fallback):
    if value.get('kind') not in LIFECYCLE_KINDS:
        return DevelopmentFault(fallback)
    operation = 'restart' if value['kind'] == 'vm_restart' else 'stop'
    phase = value.get('phase') or 'unknown'
    job = identity(value.get('jobId'))
    return DevelopmentFault(f'VM {operation} job {job} has an unconfirmed outcome in phase {phase}. '
                            'For a running VM, use System → Virtual Machines → Restart. '
                            'Confirm the new boot and check SSH access before continuing.',
                            reason_code='vm_lifecycle_recovery_required')


def require_clear(projects, vm_id):
    value = read(path(projects, vm_id))
    if value is not None:
        raise recovery_fault(value, 'Resolve the original unconfirmed guest effect before a VM lifecycle action.')


def admission(projects, vm_id, state):
    file = path(projects, vm_id)
    if not file.exists() and not file.is_symlink(): return
    with locked(file):
        value = read(file)
        if value is None: return
        if state == 'stopped':
            archive(file, value, 'VM confirmed stopped; no guest action replayed')
            return
        raise recovery_fault(value, 'A previous execution has no confirmed cleanup receipt. Reconcile it or explicitly stop the assigned VM before another development job.')


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


def lifecycle_status(store, job, access):
    """Relate the original recovery record to the currently observed VM boot."""
    from access import same_host_image, vm_config

    if job['kind'] not in LIFECYCLE_KINDS or job['state'] != 'unknown': return None
    binding = job.get('binding') or {}
    vm_id = binding.get('id')
    if vm_id is None or store.project['vmId'] != vm_id:
        return {'state':'binding_changed', 'jobId':job['id']}
    vm = vm_config(store.r4os, vm_id)
    fields = {'vmId':'id', 'vmRevision':'revision', 'imageId':'imageId', 'imageSha256':'imageSha256'}
    if any(binding.get(field) != vm[field] for field in fields.values()):
        return {'state':'binding_changed', 'jobId':job['id']}

    file = path(store.projects, vm_id)
    def matches(value):
        return value and (value.get('jobId'), value.get('projectId'), value.get('kind'), value.get('vmRevision')) == (
            job['id'], store.id, job['kind'], vm['revision'])

    result = {'jobId':job['id'], 'vmId':vm_id}
    active = read(file)
    row = store.db.execute('''SELECT payload FROM jobs WHERE kind='vm_restart'
        AND json_extract(payload,'$.vmLifecycle.recoveryJobId')=? ORDER BY rowid DESC LIMIT 1''', (job['id'],)).fetchone()
    reset_job = json.loads(row[0]) if row else None
    if matches(active):
        result.update(state='required', phase=active.get('phase'))
        if reset_job:
            result.update(resetJobId=reset_job['id'], resetState=reset_job['state'], resetPhase=reset_job['phase'],
                          next='Read the original hard restart job for its QEMU confirmation.')
        elif job.get('hardReset'):
            result['next'] = 'Check the QEMU evidence for this original hard restart and confirm the assigned VM state.'
        else:
            result['next'] = 'Check the assigned VM. Use hard_restart when it is running and this run permits recovery.'
        return result
    original = read(file.parent / 'Resolved' / (identity(job['id']) + '.json'))
    if not matches(original):
        return {**result, 'state':'unconfirmed', 'next':'Check the original lifecycle receipt and assigned VM state.'}
    result.update(state='released', resolvedAt=original['resolvedAt'], resolution=original['resolution'])
    proof = original.get('bootTransition') or {}
    target = original.get('target') or {}
    if (proof.get('kind') not in ('qmp_reset','new_instance') or not proof.get('bootId')
            or not target.get('bootId') or target['bootId'] == proof['bootId']
            or any(target.get(key) != vm[field] for key, field in fields.items())):
        return result
    expected = proof['bootId']
    if reset_job and reset_job['state'] == 'completed':
        from vm_lifecycle import ready_boot_id
        lifecycle = reset_job['vmLifecycle']
        reset = lifecycle.get('reset') or {}
        ready_boot = ready_boot_id(reset)
        if (reset.get('confirmed') is True and ready_boot and ready_boot == lifecycle.get('newBootId')
                and proof['bootId'] in (reset.get('bootId'), ready_boot)
                and proof.get('invocationId') == reset.get('invocationId')
                and all(lifecycle.get(key) == vm[field] for key, field in fields.items())):
            proof, expected = reset, ready_boot
            result['resetJobId'] = lifecycle['jobId']
    result['bootTransition'] = {key:proof[key] for key in ('kind','previousBootId','bootId','observedAt','guest') if key in proof}
    result['recoveryBootId'] = expected
    readiness = result['readiness'] = {'state':'boot_unconfirmed'}
    boot = access.boots.values.get(vm_id) or {}
    if not boot.get('connected') or any(boot.get(key) != vm[field] for key, field in fields.items()):
        return result
    result['currentBootId'] = boot['bootId']
    record = access.record(vm_id)
    checked = record.get('readiness') if same_host_image(record, vm) else None
    if checked and checked['vmRevision'] == vm['revision'] and checked['bootId'] == expected:
        readiness.update({key:checked[key] for key in ('bootId','checkedAt','release','kernel')})
    if boot['bootId'] != expected:
        readiness['state'] = 'historical'
    elif not boot.get('running'):
        readiness['state'] = 'boot_unconfirmed'
    else:
        status = access.public(vm_id)
        if status['ready']:
            readiness['state'] = 'ready'
        elif status['available']:
            readiness['state'] = 'required'
            result['next'] = {'action':'start', 'expectedBootId':expected}
        else:
            readiness.update(state='unavailable', reason=status['reason'])
    return result
