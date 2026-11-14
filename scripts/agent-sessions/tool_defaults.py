"""Current tool defaults; explicit saved choices and accepted runs stay intact."""
import json
import os
from pathlib import Path
import re
import stat
from profile import permission_tools, default_enabled


def private_document(path, maximum=32768):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path: raise ValueError('Linked private metadata')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum: raise ValueError('Invalid private metadata')
        return json.load(stream)


def repository_binding(store):
    """Studio's private local receipt, never portable Workspace repository text."""
    if store.owner_type != 'project': return None
    root = store.projects / store.owner_id / '.studio/git'
    try:
        value = private_document(root / 'binding.json')
        repository = value['repository']
        if (value.get('schema') != 1 or type(value.get('revision')) is not int or value['revision'] < 1
                or type(value.get('userId')) is not int or value['userId'] < 1
                or not isinstance(value.get('connectionId'), str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value['connectionId'])
                or type(repository.get('id')) is not int or repository['id'] < 1
                or not isinstance(repository.get('owner'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', repository['owner'])
                or not isinstance(repository.get('name'), str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', repository['name'])
                or not isinstance(value.get('branch'), str) or not value['branch'] or len(value['branch'].encode()) > 255
                or value['branch'].startswith(('-', '/', '.')) or value['branch'].endswith(('/', '.', '.lock'))
                or any(v in value['branch'] for v in ('..', '@{', '//', '\\'))
                or any(ord(c) <= 32 or ord(c) == 127 or c in '~^:?*[' for c in value['branch'])): return None
        # An uncertain create response does not grant the new-session default.
        receipt = root / 'create-repository.json'
        if receipt.exists() or receipt.is_symlink():
            original = private_document(receipt)
            if original.get('state') == 'intent': return None
            if original.get('state') == 'created' and original.get('repositoryId') == repository['id']:
                request = original.get('requestId')
                if not isinstance(request, str) or not re.fullmatch(r'[a-f0-9-]{36}', request): return None
                job = private_document(store.projects / '.studio/github/Jobs' / request / 'job.json')
                if (job.get('projectId') != store.owner_id or job.get('kind') != 'create_repository' or job.get('state') != 'completed'
                        or job.get('result', {}).get('binding', {}).get('repository', {}).get('id') != repository['id']): return None
        return {**{key: value[key] for key in ('revision', 'connectionId', 'userId', 'branch')},
                'repository': {key: repository[key] for key in ('id', 'owner', 'name')}}
    except (OSError, ValueError, TypeError, KeyError, AttributeError): return None


def permissions(store):
    result = {'studio.' + tool: default_enabled(tool) for tool in permission_tools(store.selected_profile)}
    bound_tools = {'studio.push_project','studio.finish_github_issue'} & result.keys()
    if bound_tools:
        bound = repository_binding(store) is not None
        for tool in bound_tools:
            result[tool] = bound
    return result


def github_credential_revision(projects, bound):
    if not bound: return None
    try:
        catalog = private_document(projects.parent / 'GitHub/connections.json', 8 * 1024 * 1024)
        if catalog.get('schema') != 1: return None
        entry = next(connection for connection in catalog['connections'] if connection.get('id') == bound['connectionId'])
        revision = entry.get('tokenRevision', 1)
        return revision if type(revision) is int and revision >= 1 else None
    except (OSError, ValueError, TypeError, KeyError, StopIteration, AttributeError):
        return None


def effective(store, saved):
    """Add newly available tools while preserving every explicit saved switch."""
    defaults = permissions(store)
    return {name: saved.get(name, enabled) for name, enabled in defaults.items()}
