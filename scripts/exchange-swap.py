#!/usr/bin/env python3
"""Atomically publish a fully journaled offline Exchange host tree."""
import ctypes
import os
from pathlib import Path
import re
import sys
parent, operation = sys.argv[1:]
if not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', operation): raise SystemExit('Invalid Exchange transaction.')
parent = Path(parent)
if parent.resolve(strict=True) != parent: raise SystemExit('Linked Exchange transaction parent.')
old, new = parent / 'Share', parent / ('.merge-' + operation)
if not old.is_dir() or not new.is_dir() or old.is_symlink() or new.is_symlink(): raise SystemExit('Invalid Exchange transaction directories.')
libc = ctypes.CDLL(None, use_errno=True)
libc.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
libc.renameat2.restype = ctypes.c_int
if libc.renameat2(-100, os.fsencode(old), -100, os.fsencode(new), 2):
    value = ctypes.get_errno(); raise OSError(value, os.strerror(value))
fd = os.open(parent, os.O_DIRECTORY)
try: os.fsync(fd)
finally: os.close(fd)
