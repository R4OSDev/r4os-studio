"""Build and identify the Studio guest adapter in its private pinned SDK project."""
import asyncio
import json
import fcntl
from pathlib import Path
import shutil
import uuid

from contracts import APP, DevelopmentFault, digest, encode, hash_value
from jobs import Jobs, folder, now
from snapshot import capture
from builder import Builder
from store import connect


async def prepare_helper(projects, r4os, execution_profile):
    source = APP / 'guest/development-helper'
    files = [{'path': str(p.relative_to(source)), 'sha256': digest(p)}
             for p in sorted(source.rglob('*')) if p.is_file() and not p.is_symlink()]
    pins = execution_profile['components']['pinSets']['Zig']
    key = hash_value({'source': files, 'pins': pins, 'protocol': 1})
    root = folder(Path(projects) / '.studio/development/Helpers' / key)
    with (root / 'build.lock').open('a') as lock:
        while True:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError: await asyncio.sleep(.2)
        return await build_locked(root, source, files, pins, key, r4os)


async def build_locked(root, source, files, pins, key, r4os):
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'r4os-studio-helper:' + key))
    project = root / project_id
    if not project.exists():
        folder(project); shutil.copytree(source, project / 'Workspace')
    actual = [{'path': str(p.relative_to(project / 'Workspace')), 'sha256': digest(p)}
              for p in sorted((project / 'Workspace').rglob('*')) if p.is_file() and not p.is_symlink()]
    if actual != files or any(p.is_symlink() for p in (project / 'Workspace').rglob('*')):
        raise DevelopmentFault('The private helper source cache differs from this Studio release.')
    db = connect(root)
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (project_id, 'Studio guest helper', '', 'Zig', 'terminal', 'STHELP', None,
                 encode(pins), now(), now(), 1, 'ready'))
    finally: db.close()
    store = Jobs(root, r4os, project_id)
    try:
        for row in store.db.execute('SELECT id,payload FROM artifacts ORDER BY rowid DESC'):
            try:
                artifact = store.artifact(row['id'])
                return {'protocol': 1, 'sourceSha256': hash_value(files), 'sha256': artifact['files'][0]['sha256'],
                        'path': store.root / 'Artifacts' / artifact['id'] / artifact['entry'],
                        'bytes': artifact['files'][0]['bytes'], 'pins': pins, 'artifact': artifact}
            except DevelopmentFault: continue
        # An interrupted helper build is never automatically resumed. A new
        # invocation can compile the same immutable helper inputs afresh.
        for row in store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchall():
            store.update(row['id'], 'unknown', error='The previous helper build ended without a receipt.')
        job, _ = store.admit('build', {'requestId': str(uuid.uuid4()), 'projectRevision': 1, 'settingsRevision': 1})
        snapshot, directory = capture(store, job); store.update(job['id'], 'running', source=snapshot, phase='compiling')
        builder = Builder(store, job)
        try: result = await asyncio.wait_for(builder.build(directory), 600)
        except BaseException:
            store.update(job['id'], 'failed', error='The pinned Studio guest helper could not be built.'); raise
        artifact = store.artifact(result['artifactId'])
        return {'protocol': 1, 'sourceSha256': hash_value(files), 'sha256': artifact['files'][0]['sha256'],
                'path': store.root / 'Artifacts' / artifact['id'] / artifact['entry'],
                'bytes': artifact['files'][0]['bytes'], 'pins': pins, 'artifact': artifact}
    finally: store.close()
