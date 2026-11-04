"""Original source jobs run in private units with complete process-group cleanup."""
import asyncio
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from owner import skills_root
from session_store import identity
from store import ProjectFault

spec = importlib.util.spec_from_file_location('coordinator_skill_source_store', Path(__file__).resolve().parents[1] / 'skills/store.py')
packages = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = packages
spec.loader.exec_module(packages)
TERMINAL = ('complete', 'failed', 'cancelled', 'unknown')


async def unit(*args):
    child = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', *args,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    raw, _ = await asyncio.wait_for(child.communicate(), 20)
    if child.returncode or len(raw) > 8192:
        raise ProjectFault('The original source unit could not be controlled or observed.', 503)
    return raw.decode()


async def state(rid):
    raw = await unit('show', 'r4os-studio-skill-source@' + identity(rid) + '.service',
                     '--property=ActiveState,SubState,MainPID,ExecMainCode,ExecMainStatus,InvocationID')
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


async def watch(host, ident, rid, launch):
    root = skills_root(host.config['projects'])
    try:
        if launch:
            await unit('start', 'r4os-studio-skill-source@' + rid + '.service')
        while True:
            original = await state(rid)
            if original.get('ActiveState') not in ('active', 'activating', 'deactivating', 'reloading'):
                break
            await asyncio.sleep(1)
        with closing(packages.connect(root)) as db:
            value = packages.sources.read_job(db, ident, rid, packages)
            invocation = value.get('invocationId')
            if invocation and original.get('InvocationID') not in ('', invocation):
                raise ProjectFault('The observed unit belongs to another original source process.', 409)
            # No download/build/publish replay: reconcile the original completed
            # unit's filesystem/SQLite publication only.
            parent=str(Path(__file__).resolve().parents[1]/'skills')
            if parent not in sys.path:sys.path.append(parent)
            import source_publish as publication
            recovered=publication.reconcile(packages,db,root,ident,value)
            if recovered and recovered['phase']=='complete':
                value.update(phase='complete',error=None,result=dict(value.get('result') or {},published=True,
                    packageHash=recovered['packageHash'],reconciled=True))
            elif recovered and recovered['phase']=='rolled_back':
                value.update(phase='failed',error='The original publication was interrupted. Its previous draft and active version were restored without replay.')
            if value['phase'] not in TERMINAL:
                value.update(phase='failed' if value['phase'] == 'queued' else 'unknown',
                             error='The original source helper ended without a final receipt. No replacement was started.')
            value.update(pid=None, processEndConfirmed=True, unitState=original, updatedAt=packages.now())
            with db:
                db.execute('UPDATE skill_source_jobs SET metadata=? WHERE request_id=?', (packages.encode(value), rid))
                source = packages.sources.read(db, ident)
                if source and source.get('lastRequestId') == rid and value['phase'] != 'complete':
                    source.update(status=value['phase'], updatedAt=value['updatedAt'])
                    db.execute('UPDATE skill_sources SET metadata=? WHERE skill_id=?', (packages.encode(source), ident))
            import source_retention
            collected=source_retention.prune(packages,db,root,ident)
            value['cleanup']=collected
            with db:db.execute('UPDATE skill_source_jobs SET metadata=? WHERE request_id=?',(packages.encode(value),rid))
    except asyncio.CancelledError:
        raise
    except Exception:
        return  # A later coordinator observes the original; never replay a download.


async def start(host, ident, rid):
    identity(ident)
    identity(rid)
    root = skills_root(host.config['projects'])
    try:
        with closing(packages.connect(root)) as db:
            if packages.lifecycle.deleted(root,ident) or not db.execute("SELECT 1 FROM skills WHERE id=? AND state='ready'",(ident,)).fetchone():
                raise packages.SkillFault('The source owner is unavailable.',404)
            value = packages.sources.read_job(db, ident, rid, packages)
    except packages.SkillFault as error:
        raise ProjectFault(str(error), error.code) from None
    if rid in host.source_tasks or value.get('processEndConfirmed') or len(host.source_tasks) >= 2:
        return value
    if value['phase'] in TERMINAL and not value.get('invocationId'):
        return value
    task = asyncio.create_task(watch(host, ident, rid, value['phase'] == 'queued'))
    host.source_tasks[rid] = task
    task.add_done_callback(lambda _, rid=rid: host.source_tasks.pop(rid, None))
    return value


async def dispatch(host):
    root = skills_root(host.config['projects'])
    path = root / 'Skills.sqlite'
    if not path.exists() or len(host.source_tasks) >= 2:
        return
    if path.resolve(strict=True) != path:
        raise ProjectFault('Invalid skill catalog.', 503)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='skill_source_jobs'").fetchone():
            return
        rows = db.execute('SELECT skill_id,request_id,metadata FROM skill_source_jobs ORDER BY rowid DESC LIMIT 256').fetchall()
    for ident, rid, raw in reversed(rows):
        if len(host.source_tasks) >= 2:
            break
        value = json.loads(raw)
        if (not value.get('processEndConfirmed') and (value['phase'] == 'queued' or value.get('invocationId'))
                and not packages.lifecycle.deleted(root, ident)):
            await start(host, ident, rid)
