"""One explicit saved-source commit and a non-forced single-ref push with readback."""
from common import ProjectFault, document, binding, source_path, save, now


def receipt(action, result):
    parent = action.base / 'Receipts'; parent.mkdir(mode=0o700, exist_ok=True)
    save(parent / (action.job['id'] + '.json'), {'schema': 1, 'requestId': action.job['id'], 'repositoryId': action.bound['repository']['id'],
         'branch': action.bound['branch'], 'bindingRevision': action.bound['revision'], 'result': result, 'confirmedAt': now()})
    return result


def push(action, data):
    if set(data) - {'bindingRevision', 'snapshot', 'commitMessage', 'files'} or not isinstance(data.get('commitMessage'), str) or not data['commitMessage'].strip() or len(data['commitMessage'].encode()) > 4000 or '\x00' in data['commitMessage']:
        raise ProjectFault('Enter a commit description (1–4,000 UTF-8 bytes).', 400)
    if not action.bound or data.get('bindingRevision') != action.bound['revision']: raise ProjectFault('Repository binding changed. Refresh before pushing.', 409)
    old_remote = document(action.base / 'remote.json') if (action.base / 'remote.json').exists() else {}
    action.progress('checking_push')
    state = action.status(True)
    if action.remote['archived']: raise ProjectFault('Archived repositories cannot accept a push.', 409)
    if state['snapshot'] != data.get('snapshot'): raise ProjectFault('Saved source files changed. Refresh and review them before pushing.', 409)
    if state['state'] in ('behind', 'diverged', 'remote_only') or (state['state'] == 'branch_missing' and old_remote.get('head')):
        raise ProjectFault('Remote history changed. Review Pull or import before pushing; local commits were preserved.', 409)
    from project_maintenance import project
    from git_metadata import portable
    metadata = action.workspace / '.r4os-studio/project.json'
    if metadata.exists() and document(metadata, 65536) != portable(project(action.projects, action.id)):
        raise ProjectFault('Portable project pins differ from this project. Resolve the metadata before pushing.', 409)
    changes = {v['path'] for v in state['changes']}
    selected = data.get('files', sorted(changes))
    if not isinstance(selected, list) or len(selected) > 10000 or any(not isinstance(v, str) for v in selected) or len(set(selected)) != len(selected): raise ProjectFault('Select a bounded list of changed relative source files.', 400)
    for path in selected:
        source_path(path)
        if path not in changes: raise ProjectFault('The selected file list changed. Refresh before pushing.', 409)
    head = state['head']; committed = False
    action.git.run('read-tree', head) if head else action.git.run('read-tree', '--empty')
    if selected:
        action.git.run('add', '--all', '--pathspec-from-file=-', '--pathspec-file-nul', data=('\x00'.join(selected) + '\x00').encode())
    tree = action.git.text('write-tree')
    if action.status()['snapshot'] != state['snapshot']: raise ProjectFault('Sources changed during commit preparation. Review them again.', 409)
    old_tree = action.git.text('rev-parse', head + '^{tree}') if head else None
    if selected and tree != old_tree:
        author = action.bound['author']
        action.progress('preparing_commit', previousHead=head, preparedTree=tree)
        args = ['-c', 'user.name=' + author['name'], '-c', 'user.email=' + author['email'], 'commit-tree', tree]
        if head: args += ['-p', head]
        commit = action.git.text(*args, data=(data['commitMessage'].strip() + '\n').encode())
        action.progress('commit_prepared', preparedCommit=commit, effectPossible=True)
        action.git.run('update-ref', 'HEAD', commit, head or '0' * 40)
        head, committed = commit, True
        action.progress('local_commit_confirmed', effectPossible=False)
    if head is None: return receipt(action, {'pushed': False, 'nothingToPush': True, 'commit': None, 'remoteHead': state['remoteHead'], 'committed': False})
    if action.status()['snapshot'] != state['snapshot']: raise ProjectFault('Sources changed after the local commit. It was retained; review before pushing.', 409)
    if head == state['remoteHead']: return receipt(action, {'pushed': False, 'nothingToPush': True, 'commit': head, 'remoteHead': head, 'committed': False})
    action.api.assert_current()
    action.progress('pushing', pushCommit=head, expectedRemote=state['remoteHead'], effectPossible=True)
    url = 'https://github.com/' + action.remote['fullName'] + '.git'
    action.git.run('push', '--porcelain', '--no-follow-tags', url, head + ':refs/heads/' + action.bound['branch'], timeout=120)
    action.progress('verifying_push')
    remote = action.fetch()
    if remote != head and (not remote or action.git.run('merge-base', '--is-ancestor', head, remote, allow=(0, 1))[1] != 0):
        raise ProjectFault('The pushed commit was not confirmed remotely. Reconcile this original operation.', 503)
    save(action.base / 'remote.json', {'head': remote, 'checkedAt': now(), 'bindingRevision': action.bound['revision']})
    action.api.assert_current()
    return receipt(action, {'pushed': True, 'nothingToPush': False, 'committed': committed, 'commit': head, 'remoteHead': remote})


def reconcile(action):
    saved = action.base / 'Receipts' / (action.job['id'] + '.json')
    if saved.exists():
        value = document(saved)
        if action.bound and value['repositoryId'] == action.bound['repository']['id'] and value['branch'] == action.bound['branch']: return value['result']
        return None
    expected = action.job.get('preparedCommit') or action.job.get('pushCommit')
    if not expected:
        if action.git.head() == action.job.get('previousHead'): return {'pushed': False, 'committed': False, 'localCommitOnly': True, 'commit': action.git.head()}
        return None
    if action.git.head() != expected: return None
    if not action.job.get('pushCommit'): return receipt(action, {'pushed': False, 'committed': True, 'localCommitOnly': True, 'commit': expected})
    remote = action.fetch()
    if remote == expected or (remote and action.git.run('merge-base', '--is-ancestor', expected, remote, allow=(0, 1))[1] == 0):
        return receipt(action, {'pushed': True, 'committed': bool(action.job.get('preparedCommit')), 'commit': expected, 'remoteHead': remote, 'reconciled': True})
    if remote == action.job.get('expectedRemote'):
        return receipt(action, {'pushed': False, 'committed': bool(action.job.get('preparedCommit')), 'commit': expected, 'remoteHead': remote, 'localCommitOnly': True, 'reconciled': True})
    return None
