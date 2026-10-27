#!/usr/bin/env python3
"""Read-only public catalog view for the credential-free worker coordinator."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
from catalog import APPLICATION_ID, CatalogFault, identity, public, regular


def read(directory, host_id):
    identity(host_id); directory = Path(directory).absolute(); path = directory / 'RemoteHosts.sqlite'; lock = directory / '.catalog.lock'
    if directory.resolve(strict=True) != directory or path.resolve(strict=True) != path: raise CatalogFault('Remote Host metadata is unavailable.', 503)
    regular(path); regular(lock); descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try: fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError: raise CatalogFault('Remote Host metadata is busy.', 409) from None
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise CatalogFault('Remote Host metadata requires compatible storage.', 503)
            return public(db, db.execute('SELECT * FROM hosts WHERE id=?', (host_id,)).fetchone())
    finally: os.close(descriptor)


if __name__ == '__main__':
    try: print(json.dumps({'result': read(sys.argv[1], sys.argv[2])}, ensure_ascii=True))
    except Exception: print(json.dumps({'error': 'Remote Host metadata is unavailable.', 'code': 503})); sys.exit(1)
