"""Bounded, thread-local facts for reuse of a completed display verification.

Execution callers never reuse this cache. With no collector, watch is a no-op.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_active = ContextVar('component_inventory_read', default=None)
MAX_FACTS = 8192


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _fact(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    try:
        resolved = path.resolve(strict=True)
        target = (str(resolved), _signature(resolved.stat())) if resolved != path else None
    except FileNotFoundError:
        target = ('missing-target', None)
    return (_signature(info), target)


class ReadFacts:
    def __init__(self):
        self.files = {}
        self.valid = True
        self.changed = False

    def watch(self, path):
        path = Path(path).absolute()
        if path not in self.files and len(self.files) >= MAX_FACTS:
            self.valid = False
            return
        try:
            actual = _fact(path)
            if path in self.files and self.files[path] != actual:
                self.valid = False
                self.changed = True
            else:
                self.files[path] = actual
        except OSError:
            self.valid = False

    def unchanged(self):
        try:
            if not all(_fact(path) == value for path, value in self.files.items()):
                self.changed = True
                return False
            return self.valid
        except OSError:
            return False


def watch(path):
    facts = _active.get()
    if facts is not None:
        facts.watch(path)


@contextmanager
def collect():
    facts = ReadFacts()
    token = _active.set(facts)
    try:
        yield facts
    finally:
        _active.reset(token)
