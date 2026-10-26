"""Release-bound Git actions. Credentials and object-store paths stay private."""
from pathlib import Path
from common import ProjectFault, storage, binding, branch, inventory, digest, save, now, project_id
from git import Git
from github import GitHub


class Operations:
    def __init__(self, config, job):
        self.config, self.job = config, job
        self.projects = Path(config['projects']); self.id = project_id(job['projectId'])
        self.base = storage(self.projects, self.id)
        self.repo = self.base / 'Repo'; self.repo.mkdir(mode=0o700, exist_ok=True)
        self.temporary = self.base / 'Temp'; self.temporary.mkdir(mode=0o700, exist_ok=True)
        self.workspace = self.projects / self.id / 'Workspace'
        self.git = Git(self.repo, self.workspace, self.temporary)
        self.bound = binding(self.projects, self.id)

    def progress(self, phase, **extra):
        self.job.update(phase=phase, updatedAt=now(), **extra)
        save(Path(self.config['projects']) / '.studio/github/Jobs' / self.job['id'] / 'job.json', self.job)

    def authorize(self):
        if not self.bound: raise ProjectFault('Connect this project to GitHub first.', 409)
        self.api = GitHub(self.config['github'], self.bound['connectionId'], expected_user=self.bound['userId'])
        repo = self.bound['repository']
        self.remote = self.api.repository(repo['owner'], repo['name'], repo['id'])
        self.git.token = self.api.token
        return self.api

    def initialize(self):
        self.git.init(self.bound['branch'] if self.bound else 'main')
        return {'initialized': True}

    def bind(self, data):
        if (set(data) - {'expectedRevision', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch', 'author'}
                or not isinstance(data.get('tokenRevision'), int) or data['tokenRevision'] < 1
                or not isinstance(data.get('userId'), int) or data['userId'] < 1
                or not isinstance(data.get('repository'), dict) or not isinstance(data['repository'].get('id'), int)):
            raise ProjectFault('Invalid GitHub binding request.', 400)
        expected = data.get('expectedRevision')
        if expected != (self.bound['revision'] if self.bound else None): raise ProjectFault('GitHub binding changed. Reload before reconnecting.', 409)
        identity = project_id(data.get('connectionId')); target_branch = branch(data.get('branch'))
        api = GitHub(self.config['github'], identity, data.get('tokenRevision'), data.get('userId'))
        candidate = data.get('repository', {})
        repo = api.repository(candidate.get('owner'), candidate.get('name'), candidate.get('id'))
        self.git.token = api.token; self.git.init(target_branch)
        current_head = self.git.head()
        if self.git.text('symbolic-ref', '--short', 'HEAD') != target_branch:
            if current_head: raise ProjectFault('Import the desired branch instead of switching existing local history.', 409)
            self.git.run('symbolic-ref', 'HEAD', 'refs/heads/' + target_branch)
        remote_sha = self.git.text('ls-remote', '--heads', 'https://github.com/' + repo['fullName'] + '.git', 'refs/heads/' + target_branch)
        if remote_sha:
            self.git.run('fetch', '--no-tags', '--no-recurse-submodules', 'https://github.com/' + repo['fullName'] + '.git', 'refs/heads/' + target_branch)
            remote_head = self.git.text('rev-parse', '--verify', 'FETCH_HEAD')
            # Adoption of an existing nonempty remote requires common, proven history.
            if current_head is None or self.git.run('merge-base', '--is-ancestor', current_head, remote_head, allow=(0, 1))[1] != 0:
                raise ProjectFault('The target repository is not empty and has no suitable local history. Import it instead.', 409)
        if self.bound and self.bound['branch'] != target_branch:
            raise ProjectFault('Changing the tracked branch requires an explicit new import.', 409)
        author = data.get('author') or {'name': api.user['login'], 'email': str(api.user['id']) + '+' + api.user['login'] + '@users.noreply.github.com'}
        if (not isinstance(author, dict) or not isinstance(author.get('name'), str) or not 1 <= len(author['name']) <= 120
                or not isinstance(author.get('email'), str) or not 3 <= len(author['email']) <= 254
                or any(c in author['name'] + author['email'] for c in '\r\n\x00<>') or '@' not in author['email']):
            raise ProjectFault('Enter a valid commit author name and email.', 400)
        api.assert_current()
        self.bound = {'schema': 1, 'revision': (expected or 0) + 1, 'connectionId': identity, 'userId': api.user['id'],
                      'repository': repo, 'branch': target_branch, 'author': author}
        self.progress('publishing_binding')
        save(self.base / 'binding.json', self.bound)
        return {'binding': self.bound}

    def fetch(self):
        self.authorize(); self.git.init(self.bound['branch'])
        url = 'https://github.com/' + self.remote['fullName'] + '.git'
        found = self.git.text('ls-remote', '--heads', url, 'refs/heads/' + self.bound['branch'])
        if not found: return None
        self.git.run('fetch', '--no-tags', '--no-recurse-submodules', url, 'refs/heads/' + self.bound['branch'], timeout=120)
        self.api.assert_current()
        return self.git.text('rev-parse', '--verify', 'FETCH_HEAD')

    def status(self, refresh=False):
        self.git.init(self.bound['branch'] if self.bound else 'main')
        remote_head = self.fetch() if refresh and self.bound else None
        if refresh and self.bound: save(self.base / 'remote.json', {'head': remote_head, 'checkedAt': now(), 'bindingRevision': self.bound['revision']})
        elif (self.base / 'remote.json').exists():
            from common import document
            cached = document(self.base / 'remote.json')
            if self.bound and cached.get('bindingRevision') == self.bound['revision']: remote_head = cached.get('head')
        head = self.git.head(); ahead, behind, state = 0, 0, 'not_connected' if not self.bound else 'unknown'
        if self.bound and refresh:
            if not head: state = 'not_pushed' if not remote_head else 'remote_only'
            elif not remote_head: state = 'branch_missing'
            else:
                counts = self.git.text('rev-list', '--left-right', '--count', head + '...' + remote_head).split()
                ahead, behind = (int(v) for v in counts)
                state = 'diverged' if ahead and behind else 'ahead' if ahead else 'behind' if behind else 'up_to_date'
        files = self.git.run('ls-files', '--cached', '--others', '--exclude-standard', '-z')[0].decode('utf8').split('\0')
        if len(files) > 10001: raise ProjectFault('Git source file count exceeded its limit.', 409)
        source = inventory(self.workspace, only=set(files) - {''})
        changes_raw = self.git.run('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=all')[0]
        # Renames are intentionally shown as deletion/addition to keep path parsing exact.
        changes = []; chunks = changes_raw.split(b'\0'); index = 0
        while index < len(chunks):
            item = chunks[index]; index += 1
            if not item: continue
            status, path = item[:2].decode('ascii'), item[3:].decode('utf8')
            if any(c in status for c in 'RC'):
                if index >= len(chunks): raise ProjectFault('Invalid Git status.', 503)
                old = chunks[index].decode('utf8'); index += 1
                changes.append({'path': old, 'status': 'D'})
            if path in source or 'D' in status: changes.append({'path': path, 'status': status.strip()})
            if len(changes) > 10000: raise ProjectFault('Git status exceeds its file limit.', 409)
        result = {'binding': self.bound, 'head': head, 'remoteHead': remote_head, 'ahead': ahead, 'behind': behind,
                  'state': state, 'changes': changes, 'snapshot': digest(source), 'checkedAt': now() if refresh else None}
        save(self.base / 'status.json', result)
        return result

    def execute(self):
        kind, data = self.job['kind'], self.job['input']
        if kind == 'initialize': return self.initialize()
        if kind == 'bind': return self.bind(data)
        if kind in ('status', 'check'): return self.status(kind == 'check')
        raise ProjectFault('This Git action is not available in this release.', 409)


def reconcile(config, job):
    """Readback only. More effect-specific readbacks are added with their owning actions."""
    base = storage(config['projects'], job['projectId'])
    if job['kind'] == 'initialize' and (base / 'Repo/HEAD').is_file(): return {'initialized': True}
    if job['kind'] == 'bind':
        bound = binding(config['projects'], job['projectId']); data = job['input']
        if (bound and bound['revision'] == (data.get('expectedRevision') or 0) + 1
                and bound['connectionId'] == data.get('connectionId') and bound['userId'] == data.get('userId')
                and bound['repository']['id'] == data.get('repository', {}).get('id') and bound['branch'] == data.get('branch')):
            return {'binding': bound}
    if job['kind'] in ('status', 'check'): return Operations(config, job).status(False)
    return None
