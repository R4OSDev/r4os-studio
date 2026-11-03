"""Cross-process project lifetime: readers/workers share; deletion owns exclusively."""
import fcntl
import os
from pathlib import Path
import re
import stat
from store import ProjectFault


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise ProjectFault('Invalid project identity.', 400)
    return value


def acquire(projects, identity, exclusive=False, pins_recovery=False):
    from sdk_migration_guard import check
    check(projects)
    project_id(identity)
    parent = Path(projects).absolute() / '.studio/project-use'
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.resolve(strict=True) != parent or not stat.S_ISDIR(parent.lstat().st_mode):
        raise ProjectFault('Invalid project reservation storage.', 503)
    file = parent / (identity + '.lock')
    descriptor = os.open(file, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    stream = os.fdopen(descriptor, 'a')
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode): raise ProjectFault('Invalid project reservation.', 503)
        fcntl.flock(stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        gate = Path(projects).absolute() / '.studio/project-pins' / (identity + '.json')
        if not pins_recovery and (gate.exists() or gate.is_symlink()):
            raise ProjectFault('Finish the original pin change in Project Settings → Pins before using this project.', 409)
        return stream
    except BlockingIOError:
        stream.close()
        raise ProjectFault('The project is in use. Stop its runs and development jobs, then retry.', 409) from None
    except BaseException:
        stream.close(); raise
