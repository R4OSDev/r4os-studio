"""One catalogue gate for admission/delete; per-owner locks protect directories."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

@contextmanager
def lock(root,exclusive=False,ident=None,fault=RuntimeError):
    root=Path(root).absolute()
    if not root.exists() and not exclusive:yield;return
    directory=root/'.locks';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if directory.resolve(strict=True)!=directory:raise fault('The skill lifecycle lock is linked.',503)
    fd=os.open(directory/(ident or 'catalog-lifecycle'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise fault('Invalid skill lifecycle lock.',503)
        try:fcntl.flock(stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:raise fault('The skill catalogue is changing. Retry after this operation.',423) from None
        yield

def deleted(root,ident):return (Path(root)/'.deleted'/(ident+'.json')).is_file()
