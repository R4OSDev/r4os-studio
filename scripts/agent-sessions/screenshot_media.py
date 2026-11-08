"""Read registered original VM pixels without creating another image receipt."""
import base64
import json
import os
import sqlite3
import stat
import zlib

from session_store import identity
from store import ProjectFault


def reference(meta):
    return 'studio-image:'+identity(meta['jobId'])+'/'+identity(meta['id'])


def read(store, sid, value, expected=None):
    store.row(sid)
    if store.owner_type != 'project':
        raise ProjectFault('This owner has no registered VM screenshots.', 403)
    try:
        job, evidence = value.removeprefix('studio-image:').split('/')
        if value != 'studio-image:'+identity(job)+'/'+identity(evidence): raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ProjectFault('Use the complete original VM screenshot reference.', 400) from None
    from session_delete import read_db
    from screenshot_gallery import BOUNDS, project, source_rows
    root = store.workspace.parent/'Development'
    try:
        with read_db(root/'Development.sqlite') as source:
            source.execute('BEGIN')
            rows = source_rows(source, 'e.id=? AND e.job_id=?', (evidence, job))
            qualified = list(project(store, source, rows, sid))
            if len(qualified) != 1 or qualified[0][1] is None:
                raise ProjectFault('This screenshot has no original capture receipt for this owner/session.', 403)
            meta = json.loads(rows[0]['payload'])
            if expected is not None and meta != expected:
                raise ProjectFault('The original screenshot metadata changed.', 409)
        from profile import regular
        path = regular(root/'Evidence'/job/(evidence+'.png'))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != meta['bytes'] or (not 0 < info.st_size <= BOUNDS['screenshotBytes'])):
                raise ProjectFault('The original screenshot file is missing or changed.', 409)
            raw = stream.read(meta['bytes']+1)
        from vision_analysis import png
        png({'metadata':meta, 'base64':base64.b64encode(raw).decode()})
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, zlib.error):
        raise ProjectFault('The original screenshot bytes are unavailable or changed. No frame was captured or copied.', 409) from None
    return meta, raw
