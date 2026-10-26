"""Release-bound Git actions. Credentials and object-store paths stay private."""
from pathlib import Path
from common import ProjectFault, storage, binding, branch, inventory, digest, save, now, project_id, name, document, source_path
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

    def create_repository(self, data):
        if (set(data) - {'connectionId', 'tokenRevision', 'userId', 'repositoryName', 'private', 'owner'}
                or type(data.get('userId')) is not int or data['userId'] <= 0
                or type(data.get('tokenRevision')) is not int or data['tokenRevision'] < 1 or type(data.get('private')) is not bool):
            raise ProjectFault('Invalid repository creation parameters.', 400)
        identity = project_id(data['connectionId']); repo_name = name(data['repositoryName'])
        if self.bound: raise ProjectFault('This project already has a repository. Manage its binding from GitHub.', 409)
        api = GitHub(self.config['github'], identity, data['tokenRevision'], data['userId'])
        owner = name(data.get('owner') or api.user['login'], True); owner_id = api.user['id']
        personal = owner.casefold() == api.user['login'].casefold()
        if personal: owner = api.user['login']
        else:
            organization = api.request('/orgs/' + owner)
            if not isinstance(organization, dict) or type(organization.get('id')) is not int or organization['id'] <= 0 or organization.get('login', '').casefold() != owner.casefold():
                raise ProjectFault('The selected repository organization could not be verified.', 409)
            owner, owner_id = name(organization['login'], True), organization['id']
        record = self.base / 'create-repository.json'
        if record.exists():
            previous = document(record)
            if previous.get('requestId') != self.job['id'] and previous.get('state') != 'rejected':
                raise ProjectFault('An earlier repository creation needs reconciliation. Do not create another repository.', 409)
        self.progress('checking_repository')
        try: api.repository(owner, repo_name)
        except ProjectFault as error:
            if error.code != 404: raise
        else: raise ProjectFault('That repository already exists. Choose another name or import it.', 422)
        save(record, {'requestId': self.job['id'], 'state': 'intent', 'connectionId': identity, 'userId': data['userId'], 'owner': owner, 'ownerId': owner_id, 'name': repo_name, 'private': data['private']})
        self.progress('creating_repository', effectPossible=True, creationOwner=owner, creationOwnerId=owner_id)
        try: response = api.request('/user/repos' if personal else '/orgs/' + owner + '/repos', 'POST', {'name': repo_name, 'private': data['private'], 'auto_init': False})
        except ProjectFault as error:
            if error.code in (400, 401, 403, 404, 422, 429):
                save(record, {'requestId': self.job['id'], 'state': 'rejected'})
                self.progress('creation_rejected', effectPossible=False)
            raise
        repository_id = response.get('id') if isinstance(response, dict) else None
        if type(repository_id) is not int or repository_id <= 0:
            raise ProjectFault('Repository creation response was not qualified. Reconcile the original request.', 503)
        self.progress('repository_created', repositoryId=repository_id)
        if response.get('owner', {}).get('id') != owner_id:
            raise ProjectFault('Created repository owner could not be confirmed. Reconcile the original request.', 503)
        save(record, {'requestId': self.job['id'], 'state': 'created', 'repositoryId': repository_id, 'connectionId': identity,
                      'userId': data['userId'], 'owner': owner, 'ownerId': owner_id, 'name': repo_name, 'private': data['private']})
        repo = api.repository(owner, repo_name, repository_id)
        api.assert_current()
        target_branch = branch(repo['defaultBranch'] or 'main')
        self.git.init(target_branch)
        if self.git.head() is None: self.git.run('symbolic-ref', 'HEAD', 'refs/heads/' + target_branch)
        self.bound = {'schema': 1, 'revision': 1, 'connectionId': identity, 'userId': api.user['id'], 'repository': repo,
                      'branch': target_branch, 'author': {'name': api.user['login'], 'email': str(api.user['id']) + '+' + api.user['login'] + '@users.noreply.github.com'}}
        self.progress('publishing_binding')
        save(self.base / 'binding.json', self.bound)
        return {'binding': self.bound, 'notPushed': True}

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
            if current_head is None or (self.git.run('merge-base', '--is-ancestor', current_head, remote_head, allow=(0, 1))[1] != 0 and self.git.run('merge-base', '--is-ancestor', remote_head, current_head, allow=(0, 1))[1] != 0):
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
        checked_at = now() if refresh and self.bound else None
        if refresh and self.bound: save(self.base / 'remote.json', {'head': remote_head, 'checkedAt': checked_at, 'bindingRevision': self.bound['revision']})
        elif (self.base / 'remote.json').exists():
            from common import document
            cached = document(self.base / 'remote.json')
            if self.bound and cached.get('bindingRevision') == self.bound['revision']: remote_head, checked_at = cached.get('head'), cached.get('checkedAt')
        head = self.git.head(); ahead, behind, state = 0, 0, 'not_connected' if not self.bound else 'unknown'
        if self.bound and checked_at:
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
                  'state': state, 'changes': changes, 'snapshot': digest(source), 'checkedAt': checked_at, 'fresh': bool(refresh and self.bound)}
        save(self.base / 'status.json', result)
        return result

    def diff(self, data):
        if set(data) != {'path', 'snapshot'}: raise ProjectFault('Invalid diff preview request.', 400)
        path = source_path(data['path']); state = self.status()
        if state['snapshot'] != data['snapshot']: raise ProjectFault('Saved sources changed. Refresh before previewing.', 409)
        change = next((v for v in state['changes'] if v['path'] == path), None)
        if change is None: raise ProjectFault('This file has no saved source changes.', 409)
        limit = 128 * 1024; binary = False
        if 'D' in change['status'] and not (self.workspace / path).exists() and not self.git.head():
            raw, text = b'', 'Deleted file: ' + path
        elif change['status'] == '??' or not self.git.head():
            with (self.workspace / path).open('rb') as stream: raw = stream.read(limit + 1)
            try: text = raw.decode('utf8'); binary = '\x00' in text
            except UnicodeDecodeError: text, binary = '', True
            text = 'New file: ' + path + '\n\n' + text if not binary else 'Binary file added.'
        else:
            raw = self.git.run('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--no-color', 'HEAD', '--', path)[0] if self.git.head() else b''
            text = raw[:limit].decode('utf8', errors='replace')
        if self.status()['snapshot'] != state['snapshot']: raise ProjectFault('Saved sources changed during the preview. Refresh and retry.', 409)
        return {'diff': {'path': path, 'text': text[:limit], 'truncated': len(raw) > limit, 'binary': binary}}

    def execute(self):
        kind, data = self.job['kind'], self.job['input']
        if kind == 'initialize': return self.initialize()
        if kind == 'bind': return self.bind(data)
        if kind == 'create_repository': return self.create_repository(data)
        if kind == 'diff': return self.diff(data)
        if kind == 'push':
            from pushing import push
            return push(self, data)
        if kind in ('status', 'check'): return self.status(kind == 'check')
        raise ProjectFault('This Git action is not available in this release.', 409)


def reconcile(config, job):
    """Readback only. More effect-specific readbacks are added with their owning actions."""
    base = storage(config['projects'], job['projectId'])
    if job['kind'] == 'push':
        from pushing import reconcile as reconcile_push
        return reconcile_push(Operations(config, job))
    if job['kind'] == 'initialize' and (base / 'Repo/HEAD').is_file(): return {'initialized': True}
    if job['kind'] == 'bind':
        bound = binding(config['projects'], job['projectId']); data = job['input']
        if (bound and bound['revision'] == (data.get('expectedRevision') or 0) + 1
                and bound['connectionId'] == data.get('connectionId') and bound['userId'] == data.get('userId')
                and bound['repository']['id'] == data.get('repository', {}).get('id') and bound['branch'] == data.get('branch')):
            return {'binding': bound}
    if job['kind'] == 'create_repository':
        bound = binding(config['projects'], job['projectId'])
        if (bound and bound['connectionId'] == job['input']['connectionId'] and bound['userId'] == job['input']['userId']
                and bound['repository']['id'] == job.get('repositoryId')):
            return {'binding': bound, 'notPushed': True}
        # A name match alone cannot establish ownership after a lost create response.
        # A confirmed repository ID can be read back, then explicitly published by the original job.
        if job.get('repositoryId'):
            api = GitHub(config['github'], job['input']['connectionId'], expected_user=job['input']['userId'])
            repo = api.repository(job.get('creationOwner') or api.user['login'], job['input']['repositoryName'], job['repositoryId'])
            if repo['private'] != job['input']['private']: return None
            action = Operations(config, job); target_branch = branch(repo['defaultBranch'] or 'main'); action.git.init(target_branch)
            if action.git.head() is not None: return None
            action.git.run('symbolic-ref', 'HEAD', 'refs/heads/' + target_branch)
            bound = {'schema': 1, 'revision': 1, 'connectionId': job['input']['connectionId'], 'userId': api.user['id'], 'repository': repo,
                     'branch': target_branch, 'author': {'name': api.user['login'], 'email': str(api.user['id']) + '+' + api.user['login'] + '@users.noreply.github.com'}}
            api.assert_current(); save(base / 'binding.json', bound)
            return {'binding': bound, 'notPushed': True}
    if job['kind'] in ('status', 'check'): return Operations(config, job).status(False)
    return None
