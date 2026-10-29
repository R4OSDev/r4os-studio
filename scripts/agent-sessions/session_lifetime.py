"""Cross-process lifetime gate for one owner/session, held through each use."""
import fcntl
import os
import stat
from pathlib import Path
from profile import directory
from store import ProjectFault


def acquire(projects, kind, owner, sid, exclusive=False):
    from session_store import identity
    if kind not in ('project', 'skill'): raise ProjectFault('Invalid session owner.', 400)
    name = kind + '-' + identity(owner) + '-' + identity(sid)
    root = directory(Path(projects) / '.studio/agents/.session-lifetimes')
    fd = os.open(root / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    stream = os.fdopen(fd, 'a+b')
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise ProjectFault('Session lifetime storage needs maintenance.', 503)
        try: fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('This session is in use. Wait for its current operation to finish.', 423) from None
        return stream
    except BaseException:
        stream.close(); raise


def state(db, sid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='session_deletions'").fetchone(): return None
    return db.execute('SELECT phase FROM session_deletions WHERE session_id=?', (sid,)).fetchone()
