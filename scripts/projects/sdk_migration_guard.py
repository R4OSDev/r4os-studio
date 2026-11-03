"""A durable admission gate for an explicitly requested whole-SDK migration."""
from contextlib import contextmanager
import contextvars
import json
from pathlib import Path

from store import ProjectFault

_owner = contextvars.ContextVar('studio_sdk_migration_owner', default=None)


def path(projects):
    return Path(projects).absolute() / '.studio/sdk-migration.json'


def check(projects):
    gate = path(projects)
    if not gate.exists() and not gate.is_symlink():
        return
    if gate.resolve(strict=True) != gate.absolute() or not gate.is_file() or gate.stat().st_size > 65536:
        raise ProjectFault('SDK migration admission metadata needs recovery.', 503)
    value = json.loads(gate.read_text())
    if (value.get('schema') != 1 or value.get('operation') != 'sdk-profile-migration'
            or not isinstance(value.get('requestId'), str)):
        raise ProjectFault('SDK migration admission metadata needs recovery.', 503)
    if _owner.get() != (str(Path(projects).absolute()), value['requestId']):
        raise ProjectFault('An explicit SDK migration is pending. Finish its original request before using projects.', 409)


@contextmanager
def own(projects, request_id):
    """Only the local migration implementation sets this process-private scope."""
    token = _owner.set((str(Path(projects).absolute()), request_id))
    try:
        yield
    finally:
        _owner.reset(token)
