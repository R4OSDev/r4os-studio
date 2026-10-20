#!/usr/bin/env python3
"""Exchange complete VM directories atomically, without privileges or a shell."""
import ctypes
import os
from pathlib import Path
import re
import sys

parent, identity, operation = sys.argv[1:]
uuid = r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}'
if not re.fullmatch(uuid, identity) or not re.fullmatch(uuid, operation):
    raise SystemExit('Invalid VM release transaction.')
parent = Path(parent).resolve(strict=True)
old, new = parent / identity, parent / f'.release-{identity}-{operation}'
if not old.is_dir() or not new.is_dir() or old.is_symlink() or new.is_symlink():
    raise SystemExit('VM transaction directories are unavailable.')
libc = ctypes.CDLL(None, use_errno=True)
libc.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
libc.renameat2.restype = ctypes.c_int
if libc.renameat2(-100, os.fsencode(old), -100, os.fsencode(new), 2):
    value = ctypes.get_errno()
    raise OSError(value, os.strerror(value))
fd = os.open(parent, os.O_DIRECTORY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
