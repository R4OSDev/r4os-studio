#!/usr/bin/python3
"""Read only the broker's private request file. No password in argv or env."""
import os
from pathlib import Path
import re
import stat
import sys


def main():
    request = os.environ.get('STUDIO_REMOTE_REQUEST', '')
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', request): raise ValueError()
    root = Path(os.environ['STUDIO_REMOTE_AUTH_ROOT'])
    path = root / request / 'password'
    if not root.is_absolute() or path.resolve(strict=True) != path: raise ValueError()
    for directory in (root, path.parent):
        info = directory.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077: raise ValueError()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r') as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077 or not 1 <= info.st_size <= 4096: raise ValueError()
        sys.stdout.write(file.read() + '\n')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError): sys.exit(1)
