"""Project-private compiler artifacts; never a source, output or verification cache."""
import fcntl
import json
import os
from pathlib import Path
import platform
import stat
import sys

from contracts import DevelopmentFault, digest, hash_value
from jobs import folder
from layout import save


class BuildCache:
    def __init__(self, store, job):
        self.lock = None
        identity = {'schema': 1, 'projectId': store.id, 'pins': job['pins'],
                    'language': store.project['language'], 'role': store.project['template'],
                    'moduleName': store.project['moduleName'], 'host': [sys.platform, platform.machine()],
                    'builderSha256': digest(Path(__file__).with_name('builder.py')),
                    'policySha256': digest(Path(__file__))}
        key = hash_value(identity)
        self.root = folder(store.root / 'Cache' / key)
        try:
            fd = os.open(self.root / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            self.lock = os.fdopen(fd, 'r+b')
            info = os.fstat(self.lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DevelopmentFault('The compiler cache lock is invalid.')
            try: fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DevelopmentFault('Another build is using this project compiler cache. Wait for it to finish.') from None
            marker = self.root / 'cache.json'
            if marker.exists() or marker.is_symlink():
                if marker.resolve(strict=True) != marker or json.loads(marker.read_text()) != identity:
                    raise DevelopmentFault('The project compiler cache identity changed. Cached data was preserved.')
            else:
                save(marker, identity)
            for name in ('zig', 'zig-local', 'rust-build'): folder(self.root / name)
            packages = self.root / 'zig/p'
            if packages.exists() or packages.is_symlink():
                if not packages.is_symlink() or os.readlink(packages) != '/packages':
                    raise DevelopmentFault('The compiler cache package binding changed. Cached data was preserved.')
            else:
                packages.symlink_to('/packages')
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None
