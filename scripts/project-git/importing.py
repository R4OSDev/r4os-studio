"""Clone one app branch into private staging. SDK validation and registration use the existing project adapter."""
from pathlib import Path
from common import ProjectFault, project_id, folder, name, branch, document, save, inventory, digest, now
from github import GitHub
from git import Git
from trees import materialize


def prepare(config, job):
    data = job['input']; identity = project_id(job['projectId']); projects = Path(config['projects'])
    if (set(data) != {'connectionId', 'tokenRevision', 'userId', 'repository', 'branch'}
            or type(data.get('userId')) is not int or data['userId'] <= 0 or type(data.get('tokenRevision')) is not int or data['tokenRevision'] < 1
            or not isinstance(data.get('repository'), dict) or set(data['repository']) != {'id', 'owner', 'name'} or type(data['repository'].get('id')) is not int):
        raise ProjectFault('Invalid repository import request.', 400)
    if (projects / identity).exists(): raise ProjectFault('This import identity already belongs to a project.', 409)
    target_branch = branch(data['branch']); connection = project_id(data['connectionId'])
    api = GitHub(config['github'], connection, data['tokenRevision'], data['userId'])
    requested = data['repository']; repo = api.repository(requested.get('owner'), requested.get('name'), requested['id'])
    parent = projects / '.studio/github/Imports'; parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(parent)
    stage = parent / identity
    if stage.exists() or stage.is_symlink(): raise ProjectFault('Existing import staging was preserved. Reconcile the original import.', 409)
    stage.mkdir(mode=0o700); source = stage / 'Workspace'; source.mkdir(mode=0o700)
    private = stage / '.studio/git'; private.mkdir(mode=0o700, parents=True)
    objects = private / 'Repo'; objects.mkdir(mode=0o700); temporary = private / 'Temp'; temporary.mkdir(mode=0o700)
    git = Git(objects, source, temporary, api.token); git.init(target_branch)
    job_path = projects / '.studio/github/Jobs' / job['id'] / 'job.json'
    def progress(phase): job.update(phase=phase, updatedAt=now()); save(job_path, job)
    progress('fetching_import')
    url = 'https://github.com/' + repo['fullName'] + '.git'
    if not git.text('ls-remote', '--heads', url, 'refs/heads/' + target_branch): raise ProjectFault('This branch is empty or unavailable. Select a nonempty branch.', 409)
    git.run('fetch', '--no-tags', '--no-recurse-submodules', url, 'refs/heads/' + target_branch, timeout=120)
    commit = git.text('rev-parse', '--verify', 'FETCH_HEAD')
    progress('checking_import_files'); snapshot = materialize(git, commit, source)
    if not (source / 'module.R4MF').is_file(): raise ProjectFault('Import requires one supported R4OS app with module.R4MF at the repository root.', 409)
    metadata = document(source / '.r4os-studio/project.json', 65536) if (source / '.r4os-studio/project.json').exists() else None
    if metadata is not None and (metadata.get('schema') != 1 or set(metadata) != {'schema', 'language', 'template', 'moduleName', 'pins'}):
        raise ProjectFault('Portable Studio project metadata is unsupported.', 409)
    api.assert_current(); git.run('update-ref', 'HEAD', commit); git.run('read-tree', commit)
    bound = {'schema': 1, 'revision': 1, 'connectionId': connection, 'userId': api.user['id'], 'repository': repo,
             'branch': target_branch, 'author': {'name': api.user['login'], 'email': str(api.user['id']) + '+' + api.user['login'] + '@users.noreply.github.com'}}
    save(private / 'binding.json', bound)
    save(private / 'remote.json', {'head': commit, 'checkedAt': now(), 'bindingRevision': 1})
    receipt = {'schema': 1, 'requestId': job['id'], 'projectId': identity, 'commit': commit, 'snapshot': snapshot,
               'metadata': metadata, 'binding': bound, 'files': len(inventory(source))}
    save(stage / 'import.json', receipt)
    progress('import_ready')
    return preview(receipt)


def preview(receipt):
    return {'import': {key: receipt[key] for key in ('projectId', 'commit', 'snapshot', 'files', 'metadata', 'binding')}}


def reconcile(config, job):
    root = Path(config['projects'])
    for stage in (root / '.studio/github/Imports' / job['projectId'], root / '.studio/staging' / job['projectId'], root / job['projectId']):
        if (stage / 'import.json').exists():
            receipt = document(stage / 'import.json')
            if receipt['requestId'] == job['id'] and receipt['projectId'] == job['projectId'] and digest(inventory(stage / 'Workspace')) == receipt['snapshot']:
                return preview(receipt)
    return None
