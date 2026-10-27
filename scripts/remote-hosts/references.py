"""Local project references only. Global deletion cannot remove an assigned host."""
from contextlib import closing
from pathlib import Path
import sqlite3
import stat
from catalog import CatalogFault


def projects(directory, host_id):
    path = Path(directory).parent / 'Projects/Projects.sqlite'
    if not path.exists() and not path.is_symlink(): return []
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode): raise CatalogFault('Project references need local maintenance before removing this host.', 503)
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise CatalogFault('The project reference schema is unsupported.', 503)
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_remote_hosts'").fetchone(): return []
            return [{'id': row[0], 'name': row[1]} for row in db.execute('SELECT p.id,p.name FROM projects p JOIN project_remote_hosts r ON r.project_id=p.id WHERE r.host_id=? LIMIT 1001', (host_id,))]
    except sqlite3.Error: raise CatalogFault('Project references could not be verified. The host was preserved.', 503) from None
