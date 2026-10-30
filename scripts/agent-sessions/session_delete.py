"""Name-confirmed session deletion; original receipt outlives private contents."""
from contextlib import closing
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

from owner import binding, owners, skills_root
from profile import directory
from session_store import SessionStore, encode, identity, now
from session_lifetime import acquire
from skill_lifecycle import api as lifecycle
from stats_store import Source, scope as statistic_scope
from stats_lifecycle import preserve_pending
from store import ProjectFault

READ_ONLY = {'studio_list_directory','studio_read_file','studio_search','studio_read_attachment',
    'studio_read_development_job','studio_get_remote_host','studio_read_remote_job',
    'studio_read_roadmap','studio_read_update_package','studio_list_generated_images',
    'studio_read_environment_notes'}
KEEP = {'session_deletions', 'retired_session_requests'}


def has(db, table): return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


async def unit_states(units):
    from host import systemctl
    for start in range(0,len(units),128):
        batch=units[start:start+128]
        values=(await systemctl('show',*batch,'--property=ActiveState','--value')).split()
        if len(values)!=len(batch): raise ProjectFault('Original worker status could not be verified.',503)
        if any(value not in ('inactive','failed') for value in values): return True
    return False


def schema(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS session_deletions(request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL UNIQUE,fingerprint TEXT NOT NULL,revision INTEGER NOT NULL,
            scope_hash TEXT NOT NULL,phase TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL,
            runs TEXT NOT NULL,history_keys TEXT NOT NULL,created_at TEXT NOT NULL,error TEXT)''')
        db.execute('CREATE TABLE IF NOT EXISTS retired_session_requests(request_id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,session_id TEXT NOT NULL)')


def receipt(row):
    return {'requestId': row['request_id'], 'sessionId': row['session_id'],
        'state': 'deleted' if row['phase'] == 'deleted' else 'unknown' if row['error'] else 'deleting',
        'phase': row['phase'], **({'reason': row['error']} if row['error'] else {})}


def original(store, sid, rid):
    if not has(store.db, 'session_deletions'): raise ProjectFault('Session deletion receipt not found.', 404)
    row = store.db.execute('SELECT * FROM session_deletions WHERE request_id=? AND session_id=?', (identity(rid), identity(sid))).fetchone()
    if not row: raise ProjectFault('Session deletion receipt not found.', 404)
    return receipt(row) | {'creationRequestIds': [r[0] for r in store.db.execute('SELECT request_id FROM retired_session_requests WHERE session_id=?',(sid,))]}


def selections(db, sid):
    """Only exact session/run membership; deferred FKs reject unhandled references."""
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        name = row[0]
        if name in KEEP or name in ('statistic_receipts','statistic_history','statistic_reconcile'): continue
        if not re.fullmatch('[a-z_]+', name): raise ProjectFault('Session schema needs maintenance before deletion.', 503)
        columns = {c[1] for c in db.execute('PRAGMA table_info("' + name + '")')}
        if name == 'sessions': yield name, 'id=?', (sid,)
        elif 'session_id' in columns: yield name, 'session_id=?', (sid,)
        elif 'run_id' in columns: yield name, 'run_id IN (SELECT id FROM runs WHERE session_id=?)', (sid,)


def read_db(path):
    if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_nlink != 1:
        raise ProjectFault('Original external job storage is linked or unavailable.', 503)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2); db.row_factory = sqlite3.Row
    return closing(db)


def external(store, sid):
    if store.owner_type != 'project': return [], {}
    blockers = []; jobs = {}
    path = store.workspace.parent / 'Development/Development.sqlite'
    if path.exists() or path.is_symlink():
        with read_db(path) as db:
            for row in db.execute('SELECT id,busy,payload FROM jobs'):
                value = json.loads(row['payload'])
                if value.get('sessionId') != sid: continue
                if value.get('projectId') != store.owner_id: raise ProjectFault('Original job owner changed.', 503)
                jobs[identity(row['id'])] = value['kind']
                if row['busy'] or value['state'] in ('queued','starting','running','stopping'):
                    blockers.append('An original development job is still active.')
                elif value['state'] == 'unknown':
                    proof = value.get('recovery') or {}
                    saved = db.execute('SELECT receipt FROM recoveries WHERE id=? AND job_id=?', (proof.get('id'), row['id'])).fetchone() if has(db,'recoveries') else None
                    if not (value.get('kind') == 'execution' and (value.get('guestState') or {}).get('closeConfirmed') is True
                            and proof.get('guestEndConfirmed') is True and proof.get('replayed') is False
                            and proof.get('source') in ('vm-stopped','vm-replaced','private-guest-close-receipt')
                            and saved and json.loads(saved[0]) == proof):
                        blockers.append('An original development effect is unconfirmed. Reconcile that job first.')
    remote = store.workspace.parent / 'RemoteHosts/Jobs.sqlite'
    if remote.exists() or remote.is_symlink():
        with read_db(remote) as db:
            if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND state IN ('queued','starting','running','stopping','unknown') LIMIT 1", (sid,)).fetchone():
                blockers.append('An original remote operation is active or unconfirmed.')
    private = store.projects / '.studio/development'
    for folder in ('leases','Forwards','Unconfirmed'):
        for file in (private / folder).glob('*.json'):
            try: value = json.loads(file.read_text())
            except (ValueError, OSError):
                if file.stem in jobs: raise ProjectFault('An original external reservation is unconfirmed.', 503)
                continue
            target = value.get('scope') or value
            if target.get('jobId') not in jobs and not (target.get('projectId') == store.owner_id and target.get('sessionId') == sid): continue
            if file.resolve(strict=True) != file: raise ProjectFault('Original external reservation is linked.', 503)
            if folder == 'Unconfirmed' or folder == 'leases' and not value.get('closedAt') or folder == 'Forwards' and value.get('state') != 'closed':
                blockers.append('An original VM effect or reservation still needs reconciliation.')
    for file in (store.projects / '.studio/github/Jobs').glob('*/job.json'):
        try: value = json.loads(file.read_text())
        except (OSError, ValueError): continue
        agent = value.get('agent') or {}
        if value.get('projectId') == store.owner_id and agent.get('sessionId') == sid and value.get('state') in ('queued','starting','running','stopping','unknown'):
            blockers.append('An original Git operation is active or unconfirmed.')
    return blockers, jobs


async def inspect(host, store, sid):
    sid = identity(sid)
    database = store.directory/'Sessions.sqlite'
    if database.stat().st_nlink != 1 or database.stat().st_uid != os.geteuid():
        raise ProjectFault('Session catalog identity needs maintenance before deletion.',503)
    row = store.db.execute('SELECT * FROM sessions WHERE id=? AND project_id=?', (sid, store.owner_id)).fetchone()
    if not row: raise ProjectFault('Session not found.', 404)
    if has(store.db,'session_deletions') and store.db.execute('SELECT 1 FROM session_deletions WHERE session_id=?',(sid,)).fetchone():
        raise ProjectFault('This session already has an original deletion request. Read that receipt.',409)
    blockers = []; runs = set()
    api=json.loads(row['engine']).get('api')
    if api:
        from api_provider_store import ApiProviders
        if ApiProviders(host.config['providers']).held_session(api['providerId'],store.owner_type,store.owner_id,sid):
            blockers.append('An original API admission or transport is unconfirmed. Reconcile or disconnect that provider before deleting its evidence.')
    for run in store.db.execute('SELECT * FROM runs WHERE session_id=?', (sid,)):
        runs.add(identity(run['id']))
        if run['busy'] or run['state'] in ('queued','starting','running','stopping'):
            blockers.append('An original agent run is still active.')
        worker = json.loads(run['worker'] or '{}')
        if worker.get('pid'):
            from attachment_store import birth
            try:
                if birth(worker['pid']) == worker.get('birth') and (Path('/proc')/str(worker['pid'])).stat().st_uid == host.config['uid']:
                    blockers.append('The original session worker is still alive.')
            except (OSError, ValueError): pass
    for file in host.root.glob('*/worker.json'):
        try: meta = host.metadata(file)
        except Exception:
            if file.parent.name in runs: raise ProjectFault('An original session worker record is unconfirmed.',503)
            continue
        if file.parent.name in runs and (binding(meta) != (store.owner_type,store.owner_id) or meta['sessionId'] != sid):
            raise ProjectFault('An original session worker belongs to another scope.',503)
        if binding(meta) != (store.owner_type,store.owner_id) or meta['sessionId'] != sid: continue
        runs.add(identity(meta['runId']))
    if await unit_states(['r4os-studio-agent@'+rid+'.service' for rid in sorted(runs)]):
        blockers.append('An original session worker unit is active.')
    if host.unbound: blockers.append('Reconcile unbound original workers before deletion.')
    if has(store.db,'session_messages') and store.db.execute("SELECT 1 FROM session_messages WHERE session_id=? AND state IN ('queued','dispatching','pending','unknown') LIMIT 1",(sid,)).fetchone():
        blockers.append('A queued, pending or unconfirmed message still belongs to this session.')
    if has(store.db,'goal_commands') and store.db.execute("SELECT 1 FROM goal_commands WHERE session_id=? AND state='pending' LIMIT 1",(sid,)).fetchone():
        blockers.append('An original Goal command is still pending.')
    if has(store.db,'session_goals'):
        goal = store.db.execute('SELECT phase,native FROM session_goals WHERE session_id=?',(sid,)).fetchone()
        if goal and (goal['phase'] != 'idle' or json.loads(goal['native'] or '{}').get('status') == 'active'):
            blockers.append('Pause or stop the Goal and confirm its original receipt first.')
    if has(store.db,'session_attachments') and store.db.execute("SELECT 1 FROM session_attachments WHERE session_id=? AND state NOT IN ('ready','removed') LIMIT 1",(sid,)).fetchone():
        blockers.append('An attachment operation is active or unconfirmed.')
    for tool in store.db.execute("SELECT t.* FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.state IN ('intent','unknown')",(sid,)):
        if tool['tool'] in READ_ONLY: continue
        from goal_recovery import development
        proof = development(store, sid, tool)
        if not proof or not (proof.get('recovery') or {}).get('guestEndConfirmed'):
            blockers.append('An original tool effect is unconfirmed. Reconcile it before deleting the evidence.')
    additional, jobs = external(store, sid); blockers.extend(additional)
    units=[]
    for job_id, kind in jobs.items():
        unit = ('r4os-studio-development@' if kind in ('build','package') else 'r4os-studio-development-vm@') + job_id + '.service'
        units.append(unit)
    if await unit_states(units): blockers.append('An original development worker unit is still active.')
    tree = hashlib.sha256(); tree.update(encode(sorted(runs)).encode())
    for table, where, args in selections(store.db, sid):
        tree.update(table.encode())
        for value in store.db.execute('SELECT * FROM "'+table+'" WHERE '+where+' ORDER BY rowid',args):
            tree.update(encode(list(value)).encode()+b'\n')
    path = store.directory / sid; device = inode = 0; history = []
    if path.exists() or path.is_symlink():
        if path.resolve(strict=True) != path or not path.is_dir(): raise ProjectFault('Session directory identity is unconfirmed.',503)
        info = path.stat(); device, inode = info.st_dev, info.st_ino
        for parent, dirs, files in os.walk(path,followlinks=False):
            dirs[:] = sorted(dirs)
            for name in sorted(dirs+files):
                child = Path(parent)/name; info = child.lstat()
                tree.update(encode([str(child.relative_to(path)),info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]).encode())
                if name.endswith('.jsonl') and row['thread_id'] and child.is_relative_to(path/'Codex'):
                    history.append(hashlib.sha256(encode({'session':sid,'thread':row['thread_id'],'file':str(child.relative_to(path/'Codex'))}).encode()).hexdigest())
    tree.update(encode([device,inode]).encode())
    public = {'sessionId':sid,'name':row['name'],'revision':row['revision'],'scopeHash':tree.hexdigest(),
        'allowed':not blockers,'blockers':list(dict.fromkeys(blockers))[:32]}
    return public, {'device':device,'inode':inode,'runs':sorted(runs),'history':history}


async def preview(host, kind, owner, sid):
    store = SessionStore(host.config['projects'],host.config['r4os'],owner,kind)
    try:
        with acquire(store.projects,kind,owner,sid,True): return (await inspect(host,store,sid))[0]
    finally: store.close()


async def delete(host, kind, owner, sid, data):
    if (not isinstance(data,dict) or set(data) != {'requestId','revision','scopeHash','confirmName'}
            or type(data['revision']) is not int or not isinstance(data['confirmName'],str)
            or not isinstance(data['scopeHash'],str) or not re.fullmatch('[a-f0-9]{64}',data['scopeHash'])):
        raise ProjectFault('Invalid confirmed session deletion.',400)
    sid=identity(sid);rid=identity(data['requestId'])
    fingerprint=hashlib.sha256(encode({'owner':{'type':kind,'id':owner},'sessionId':sid,**data}).encode()).hexdigest()
    store=SessionStore(host.config['projects'],host.config['r4os'],owner,kind)
    try:
        schema(store.db)
        previous=store.db.execute('SELECT * FROM session_deletions WHERE request_id=?',(rid,)).fetchone()
        if previous:
            if previous['session_id'] != sid or previous['fingerprint'] != fingerprint: raise ProjectFault('This request ID belongs to another deletion.',409)
            return original(store,sid,rid)
        with lifecycle.lock(skills_root(store.projects),fault=ProjectFault), acquire(store.projects,kind,owner,sid,True):
            current,private=await inspect(host,store,sid)
            if not current['allowed']: raise ProjectFault(current['blockers'][0],409)
            if data['revision'] != current['revision'] or data['scopeHash'] != current['scopeHash'] or data['confirmName'] != current['name']:
                raise ProjectFault('The session or deletion scope changed. Reload and confirm its current name again.',409)
            # The exclusive gate is borrowed by numeric capture, never reacquired.
            store.session_uses[sid]=None
            from usage_stats import Usage
            Usage(store,sid).scan(); Source(store).flush(include_acknowledged=True)
            preserve_pending(store.projects,store.directory/'Sessions.sqlite')
            with store.db:
                store.db.execute('INSERT INTO session_deletions VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)',
                    (rid,sid,fingerprint,data['revision'],data['scopeHash'],'reserved',private['device'],private['inode'],encode(private['runs']),encode(private['history']),now()))
            return original(store,sid,rid)
    finally: store.close()


def remove(path):
    if not path.exists() and not path.is_symlink(): return
    if path.is_symlink() or path.parent.resolve(strict=True) != path.parent:
        raise ProjectFault('A session cleanup target changed. Existing data was preserved.',503)
    if path.is_dir():
        if not shutil.rmtree.avoids_symlink_attacks: raise ProjectFault('Safe session cleanup is unavailable.',503)
        shutil.rmtree(path)
    elif path.is_file(): path.unlink()
    else: raise ProjectFault('An unexpected session cleanup target was preserved.',503)


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


async def finish(host,store,row):
    sid=row['session_id'];rid=row['request_id'];source=store.directory/sid
    stage=directory(store.directory/'.deleting')/rid
    present=source if source.exists() or source.is_symlink() else stage
    if present.exists() or present.is_symlink():
        if (present.resolve(strict=True) != present or not present.is_dir()
                or (present.stat().st_dev,present.stat().st_ino) != (row['device'],row['inode'])):
            raise ProjectFault('Original session directory identity changed. Existing data was preserved.',503)
    elif row['phase']=='reserved' and row['inode']:
        raise ProjectFault('Original session directory is missing. Existing data was preserved.',503)
    if row['phase']=='reserved':
        if source.exists():
            if stage.exists(): raise ProjectFault('Session staging path is occupied.',503)
            os.rename(source,stage);sync(store.directory);sync(stage.parent)
        with store.db: store.db.execute("UPDATE session_deletions SET phase='staged' WHERE request_id=?",(rid,))
    elif source.exists() or source.is_symlink(): raise ProjectFault('A retired session directory reappeared.',503)
    # Keep project development artifacts/receipts and numeric lifetime aggregates.
    if await unit_states(['r4os-studio-agent@'+identity(rid)+'.service' for rid in json.loads(row['runs'])]):
        raise ProjectFault('An original session worker is active. Existing data was preserved.',409)
    for run_id in json.loads(row['runs']):
        target=host.root/identity(run_id)
        if target.exists():
            meta=host.metadata(target/'worker.json')
            if binding(meta)!=(store.owner_type,store.owner_id) or meta['sessionId'] != sid: raise ProjectFault('Worker cleanup scope changed.',503)
            runtime=Path(host.config.get('agentRuntime','/run/r4os-studio-agents'))/run_id
            remove(runtime);remove(target)
    prefs=skills_root(store.projects)/'SessionSettings.sqlite'
    if prefs.exists() or prefs.is_symlink():
        if prefs.resolve(strict=True)!=prefs: raise ProjectFault('Session preferences are linked.',503)
        with closing(sqlite3.connect(prefs,timeout=2)) as db:
            with db: db.execute('DELETE FROM overrides WHERE owner_type=? AND owner_id=? AND session_id=?',(store.owner_type,store.owner_id,sid))
    remove(stage);sync(stage.parent)
    # One atomic catalog transaction; original create IDs become text-free tombstones.
    selected=list(selections(store.db,sid))
    with store.db:
        store.db.execute('PRAGMA secure_delete=ON');store.db.execute('PRAGMA defer_foreign_keys=ON')
        store.db.execute("INSERT OR IGNORE INTO retired_session_requests SELECT request_id,payload_hash,session_id FROM requests WHERE session_id=? AND kind='create'",(sid,))
        # Run-only children must be removed before their selected runs disappear.
        selected.sort(key=lambda item: item[0] in ('runs','sessions'))
        for table,where,args in selected: store.db.execute('DELETE FROM "'+table+'" WHERE '+where,args)
        if has(store.db,'statistic_receipts'):
            store.db.execute("DELETE FROM statistic_receipts WHERE json_extract(payload,'$.session')=?",(statistic_scope({'type':store.owner_type,'id':store.owner_id},sid),))
        if has(store.db,'statistic_history'):
            store.db.executemany('DELETE FROM statistic_history WHERE key=?',[(key,) for key in json.loads(row['history_keys'])])
        store.db.execute("UPDATE session_deletions SET phase='deleted',device=0,inode=0,runs='[]',history_keys='[]',error=NULL WHERE request_id=?",(rid,))
    return original(store,sid,rid)


async def resume(host,kind,owner,sid,rid):
    store=SessionStore(host.config['projects'],host.config['r4os'],owner,kind)
    try:
        if not has(store.db,'session_deletions'): return
        row=store.db.execute('SELECT * FROM session_deletions WHERE request_id=? AND session_id=?',(identity(rid),identity(sid))).fetchone()
        if not row or row['phase']=='deleted': return
        try:
            with lifecycle.lock(skills_root(store.projects),fault=ProjectFault), acquire(store.projects,kind,owner,sid,True):
                with store.db: store.db.execute('UPDATE session_deletions SET error=NULL WHERE request_id=?',(rid,))
                await finish(host,store,row)
                host.inboxes.discard((kind,owner,sid))
        except BaseException as error:
            with store.db: store.db.execute('UPDATE session_deletions SET error=? WHERE request_id=?',('Cleanup is unconfirmed. Read the original receipt or retry this same request.',rid))
            if isinstance(error,asyncio.CancelledError): raise
    finally: store.close()


async def recover(host):
    from store import connect
    with closing(connect(Path(host.config['projects']))) as db:
        registered=[('project',r['id']) for r in db.execute("SELECT id FROM projects WHERE state='ready'")]+owners(host.config['projects'])
    for kind,owner in registered:
        root=skills_root(host.config['projects']) if kind=='skill' else Path(host.config['projects'])
        path=root/owner/'Sessions/Sessions.sqlite'
        if not path.exists(): continue
        try:
            with read_db(path) as db:
                pending=list(db.execute("SELECT session_id,request_id FROM session_deletions WHERE phase!='deleted'")) if has(db,'session_deletions') else []
            for row in pending: await resume(host,kind,owner,row['session_id'],row['request_id'])
        except (OSError, ValueError, sqlite3.Error, ProjectFault):
            continue  # Preserve a damaged owner's originals; other owners can recover.
