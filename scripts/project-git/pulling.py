"""Checked fast-forward preparation, SDK approval and recoverable source/ref publication."""
import ctypes
import os
from pathlib import Path
from common import ProjectFault, document, folder, inventory, digest, save, now, project_id
from trees import entries, materialize


def copy_files(source, destination, files):
    for path in sorted(source.rglob('*')):
        if path.is_dir(): folder(path); (destination / path.relative_to(source)).mkdir(mode=0o700, parents=True, exist_ok=True)
    for relative, expected in files.items():
        source_path = source / relative; folder(source_path.parent)
        target = destination / relative; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(target.parent)
        descriptor = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        output = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755 if expected['executable'] else 0o644)
        import hashlib
        hashed = hashlib.sha256(); size = 0
        with os.fdopen(descriptor, 'rb') as src, os.fdopen(output, 'wb') as dst:
            while chunk := src.read(65536): size += len(chunk); hashed.update(chunk); dst.write(chunk)
            dst.flush(); os.fsync(dst.fileno())
        if size != expected['size'] or hashed.hexdigest() != expected['sha256']: raise ProjectFault('Sources changed during pull preparation.', 409)


def prepare(action, data):
    if set(data) != {'bindingRevision', 'snapshot', 'remoteHead'} or not action.bound or action.bound['revision'] != data['bindingRevision']:
        raise ProjectFault('Repository binding changed. Refresh before pulling.', 409)
    action.progress('checking_pull')
    state = action.status(True)
    if state['changes']: raise ProjectFault('Pull requires a clean saved workspace and index. Commit or preserve local changes first.', 409)
    if state['snapshot'] != data['snapshot'] or state['remoteHead'] != data['remoteHead']: raise ProjectFault('Local or remote sources changed. Refresh before pulling.', 409)
    if state['state'] == 'up_to_date': return {'nothingToPull': True, 'pulled': False, 'commit': state['head']}
    if state['state'] != 'behind': raise ProjectFault('Pull supports a confirmed fast-forward only. Diverged, missing or unrelated history was preserved.', 409)
    complete = inventory(action.workspace)
    parent = action.base / 'Pulls'; parent.mkdir(mode=0o700, exist_ok=True); folder(parent)
    total, count = 0, 0
    for path in parent.rglob('*'):
        count += 1
        if path.is_file(): total += path.stat().st_size
        if count > 50000 or total > 512 * 1024**2: raise ProjectFault('Private pull staging reached its storage limit. Review retained recovery data before another pull.', 409)
    stage = parent / action.job['id']
    if stage.exists(): raise ProjectFault('Original pull preparation was preserved. Reconcile its request.', 409)
    stage.mkdir(mode=0o700); incoming = stage / 'Incoming'; incoming.mkdir(mode=0o700)
    action.progress('preparing_pull_sources')
    materialize(action.git, state['remoteHead'], incoming)
    candidate = stage / 'New'; candidate.mkdir(mode=0o700); copy_files(action.workspace, candidate, complete)
    for path, _, _ in entries(action.git, state['head']):
        old = candidate / path
        if old.exists(): old.unlink()
        directory = old.parent
        while directory != candidate:
            try: directory.rmdir()
            except OSError: break
            directory = directory.parent
    incoming_files = inventory(incoming)
    for relative in incoming_files:
        if (candidate / relative).exists(): raise ProjectFault('An incoming file conflicts with a local ignored file. Both versions were preserved.', 409)
    copy_files(incoming, candidate, incoming_files)
    if digest(inventory(action.workspace)) != digest(complete): raise ProjectFault('Workspace changed during pull preparation.', 409)
    value = {'schema': 1, 'projectId': action.id, 'requestId': action.job['id'], 'bindingRevision': action.bound['revision'], 'repositoryId': action.bound['repository']['id'],
             'branch': action.bound['branch'], 'oldHead': state['head'], 'newHead': state['remoteHead'], 'snapshot': state['snapshot'],
             'oldSnapshot': digest(complete), 'newSnapshot': digest(inventory(candidate))}
    save(stage / 'prepare.json', value)
    return {'preparationId': action.job['id'], 'commit': value['newHead'], 'nothingToPull': False, 'pulled': False}


def exchange(left, right):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(-100, os.fsencode(left), -100, os.fsencode(right), 2) != 0: raise OSError(ctypes.get_errno(), 'Atomic workspace exchange failed.')
    for parent in (left.parent, right.parent):
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)


def apply(action, data):
    if set(data) != {'preparationId', 'bindingRevision', 'snapshot'}: raise ProjectFault('Invalid pull publication request.', 400)
    ident = project_id(data['preparationId']); stage = folder(action.base / 'Pulls' / ident)
    prepared, approved = document(stage / 'prepare.json'), document(stage / 'approval.json')
    from project_maintenance import project
    current = project(action.projects, action.id)
    if (not action.bound or data['bindingRevision'] != action.bound['revision'] or prepared['bindingRevision'] != action.bound['revision']
            or prepared['repositoryId'] != action.bound['repository']['id'] or prepared['branch'] != action.bound['branch']
            or prepared['projectId'] != action.id or data['snapshot'] != prepared['snapshot'] or approved.get('approved') is not True
            or approved.get('requestId') != ident or approved.get('projectId') != action.id or approved.get('newHead') != prepared['newHead']
            or approved.get('newSnapshot') != prepared['newSnapshot'] or approved.get('projectRevision') != current['revision'] or approved.get('pinsHash') != digest(current['pins'])):
        raise ProjectFault('Pull approval, project pins or repository binding changed. Original sources were preserved.', 409)
    state = action.status(True)
    if state['changes'] or state['head'] != prepared['oldHead'] or state['remoteHead'] != prepared['newHead'] or digest(inventory(action.workspace)) != prepared['oldSnapshot']:
        raise ProjectFault('Sources or remote history changed after the preview. Refresh before applying.', 409)
    candidate = folder(stage / 'New')
    if digest(inventory(candidate)) != prepared['newSnapshot']: raise ProjectFault('Prepared pull files changed. Existing sources were preserved.', 409)
    for directory in sorted([candidate] + [p for p in candidate.rglob('*') if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    journal = {**prepared, 'applyJobId': action.job['id'], 'phase': 'prepared'}
    save(action.base / 'pull-journal.json', journal)
    action.progress('applying_pull', preparationId=ident, effectPossible=True)
    exchange(action.workspace, candidate)
    journal['phase'] = 'exchanged'; save(action.base / 'pull-journal.json', journal)
    return complete(action, journal)


def complete(action, journal):
    head = action.git.head()
    if head == journal['oldHead']: action.git.run('update-ref', 'HEAD', journal['newHead'], journal['oldHead'])
    elif head != journal['newHead']: raise ProjectFault('Pull reference changed. Recovery data was preserved.', 409)
    action.git.run('read-tree', journal['newHead'])
    save(action.base / 'remote.json', {'head': journal['newHead'], 'checkedAt': now(), 'bindingRevision': journal['bindingRevision']})
    journal['phase'] = 'complete'; save(action.base / 'pull-journal.json', journal)
    result = {'pulled': True, 'commit': journal['newHead'], 'previousCommit': journal['oldHead'], 'preparationId': journal['requestId']}
    from pushing import receipt
    return receipt(action, result)


def reconcile(action):
    if action.job['kind'] == 'prepare_pull':
        path = action.base / 'Pulls' / action.job['id'] / 'prepare.json'
        if path.exists():
            value = document(path)
            if value['projectId'] == action.id: return {'preparationId': action.job['id'], 'commit': value['newHead'], 'nothingToPull': False, 'pulled': False}
        return {'pulled': False, 'nothingApplied': True}
    path = action.base / 'pull-journal.json'
    if not path.exists(): return {'pulled': False, 'nothingApplied': True}
    value = document(path)
    if value['applyJobId'] != action.job['id']: return None
    workspace = digest(inventory(action.workspace)); other = digest(inventory(action.base / 'Pulls' / value['requestId'] / 'New'))
    if workspace == value['newSnapshot'] and other == value['oldSnapshot']: return complete(action, value)
    if workspace == value['oldSnapshot'] and other == value['newSnapshot'] and action.git.head() == value['oldHead']:
        value['phase'] = 'aborted'; save(path, value); return {'pulled': False, 'nothingApplied': True}
    return None
