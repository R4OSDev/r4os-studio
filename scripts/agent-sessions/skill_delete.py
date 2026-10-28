"""Confirmed deletion of one skill lifetime; original receipt outlives its folder."""
import asyncio
from contextlib import closing,ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from owner import skills_root,owners,binding
from session_store import encode,identity,now
from skill_application import packages
from skill_lifecycle import api as lifecycle
from store import ProjectFault
from stats_lifecycle import preserve_pending


def schema(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS skill_deletions(request_id TEXT PRIMARY KEY,skill_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,scope_hash TEXT NOT NULL,revision INTEGER NOT NULL,phase TEXT NOT NULL,
            device INTEGER NOT NULL,inode INTEGER NOT NULL,runs TEXT NOT NULL,created_at TEXT NOT NULL,error TEXT)''')

def database(path):
    if path.resolve(strict=True)!=path or not stat.S_ISREG(path.stat().st_mode):raise ProjectFault('Skill use storage is linked or unavailable.',503)
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2);db.row_factory=sqlite3.Row
    return closing(db)

def has(db,table):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def references(value,ident):return any(entry.get('id')==ident for entry in value.get('skillAccess',{}).get('entries',[]))

def contexts(projects,ident):
    projects=Path(projects).absolute();registered=[]
    if (projects/'Projects.sqlite').is_file():
        with database(projects/'Projects.sqlite') as db:registered=[('project',r[0]) for r in db.execute("SELECT id FROM projects WHERE state='ready'")]
    registered+=owners(projects);contexts=[];own_runs=set()
    for kind,owner in registered:
        path=(skills_root(projects) if kind=='skill' else projects)/owner/'Sessions/Sessions.sqlite'
        if not path.exists():continue
        with database(path) as db:
            for run in db.execute('SELECT * FROM runs'):
                own=kind=='skill' and owner==ident
                if own:own_runs.add(identity(run['id']))
                if not own and not references(json.loads(run['config']),ident):continue
                if run['busy'] or run['state'] in ('unknown','stopping') or json.loads(run['worker'] or '{}').get('pid'):
                    contexts.append({'ownerType':kind,'ownerId':owner,'sessionId':run['session_id'],'runId':run['id'],'busy':bool(run['busy']),'state':run['state'],'worker':json.loads(run['worker'] or '{}')})
            if has(db,'session_messages'):
                for row in db.execute("SELECT * FROM session_messages WHERE mode='queue' AND state IN ('queued','dispatching')"):
                    if kind=='skill' and owner==ident or references(json.loads(row['frozen']).get('config',{}),ident):
                        contexts.append({'ownerType':kind,'ownerId':owner,'sessionId':row['session_id'],'reason':'A queued request still binds this skill revision.'})
            if has(db,'goal_commands'):
                for row in db.execute("SELECT * FROM goal_commands WHERE state='pending'"):
                    command=json.loads(row['payload'])
                    if kind=='skill' and owner==ident or command.get('action')=='play':
                        contexts.append({'ownerType':kind,'ownerId':owner,'sessionId':row['session_id'],'reason':'An original Goal command is still pending.'})
    return contexts,own_runs

def scope(db,root,ident):
    detail=packages.detail(db,root,ident);revision=detail['skill']['revision']
    revisions=[list(r) for r in db.execute('SELECT number,hash FROM revisions WHERE skill_id=? ORDER BY number',(ident,))]
    path=root/ident/'Sessions/Sessions.sqlite';session_count=0;session_ids=[];metadata=[]
    if path.exists():
        with database(path) as sessions:
            session_ids=[r[0] for r in sessions.execute('SELECT id FROM sessions ORDER BY id')];session_count=len(session_ids)
            for table in [r[0] for r in sessions.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]:
                if table.startswith('statistic') or table=='goal_clocks':continue
                if table in ('events','items','tools'):
                    metadata.append((table,*sessions.execute('SELECT COUNT(*),COALESCE(MAX(rowid),0) FROM "'+table+'"').fetchone()))
                else:
                    # User metadata is hashed privately, never returned in the preview.
                    columns={'runs':'id,state,busy,payload_hash,request_id,completed_at','sessions':'id,revision,updated_at,thread_id','session_messages':'request_id,state,input_hash','goal_commands':'request_id,state,stage,fingerprint'}.get(table,'*')
                    tree=hashlib.sha256()
                    for row in sessions.execute('SELECT '+columns+' FROM "'+table+'" ORDER BY rowid'):tree.update(encode(list(row)).encode()+b'\n')
                    metadata.append((table,tree.hexdigest()))
    inode=(root/ident).lstat()
    value={'id':ident,'revision':revision,'draft':detail['draftHash'],'revisions':revisions,'sessions':metadata,'device':inode.st_dev,'inode':inode.st_ino}
    return {'id':ident,'name':detail['skill']['name'],'revision':revision,'scopeHash':hashlib.sha256(encode(value).encode()).hexdigest(),'files':len(detail['files']),'revisions':len(revisions),'sessions':session_count,'sessionIds':session_ids,'device':inode.st_dev,'inode':inode.st_ino}

def receipt(row):return {'requestId':row['request_id'],'id':row['skill_id'],'state':'deleted' if row['phase']=='deleted' else 'unknown' if row['error'] else 'deleting','phase':row['phase'],**({'reason':row['error']} if row['error'] else {})}

def original(db,rid,ident):
    schema(db);row=db.execute('SELECT * FROM skill_deletions WHERE request_id=? AND skill_id=?',(identity(rid),identity(ident))).fetchone()
    if not row:raise ProjectFault('Skill deletion receipt not found.',404)
    return receipt(row)

async def preview(host,ident):
    root=skills_root(host.config['projects']);ident=identity(ident)
    with closing(packages.connect(root)) as db:
        current=scope(db,root,ident)
    bindings,runs=contexts(host.config['projects'],ident);blocked=[]
    for value in bindings:
        reason=value.get('reason')
        if value.get('busy'):reason='A run still owns this skill or its published resources.'
        if not reason and value.get('runId'):
            worker=value.get('worker') or {};pid=worker.get('pid')
            if pid:
                from attachment_store import birth
                try:
                    if birth(pid)==worker.get('birth') and (Path('/proc')/str(pid)).stat().st_uid==host.config['uid']:reason='The original worker may still be alive.'
                except OSError:pass
            if not reason and value['state'] in ('unknown','stopping') and await host.active_unit(value['runId']):reason='The original worker unit has not confirmed its end.'
        if reason:blocked.append({k:v for k,v in value.items() if k in ('ownerType','ownerId','sessionId','runId')}|{'reason':reason})
    # Positively attributed orphan records must not be left behind or deleted blindly.
    for path in host.root.glob('*/worker.json'):
        try:meta=host.metadata(path)
        except Exception:
            if path.parent.name in runs:raise ProjectFault('An original skill worker record is unconfirmed.',503)
            continue
        if binding(meta)!=('skill',ident):continue
        runs.add(identity(meta['runId']))
        if await host.active_unit(meta['runId']):blocked.append({'ownerType':'skill','ownerId':ident,'sessionId':meta['sessionId'],'runId':meta['runId'],'reason':'An original skill worker unit is still active.'})
    if host.unbound:blocked.append({'reason':'Reconcile unbound original workers before deleting a skill.'})
    public={k:v for k,v in current.items() if k not in ('device','inode')}
    return public|{'allowed':not blocked,'blockers':blocked[:32]},sorted(runs)

async def delete(host,ident,data):
    root=skills_root(host.config['projects']);ident=identity(ident)
    if (not isinstance(data,dict) or set(data)!={'requestId','revision','scopeHash','confirmName'} or type(data['revision']) is not int
            or not isinstance(data['scopeHash'],str) or len(data['scopeHash'])!=64 or not isinstance(data['confirmName'],str)):
        raise ProjectFault('Invalid confirmed skill deletion.',400)
    rid=identity(data['requestId']);fingerprint=hashlib.sha256(encode({'id':ident,**data}).encode()).hexdigest()
    with closing(packages.connect(root)) as db:
        schema(db);row=db.execute('SELECT * FROM skill_deletions WHERE request_id=?',(rid,)).fetchone()
        if row and (row['skill_id']!=ident or row['fingerprint']!=fingerprint):raise ProjectFault('This request ID belongs to another skill deletion.',409)
        if row:return receipt(row)
        with ExitStack() as locks:
            locks.enter_context(lifecycle.lock(root,True,fault=ProjectFault))
            locks.enter_context(lifecycle.lock(root,True,ident=ident,fault=ProjectFault))
            locks.enter_context(lifecycle.lock(root,True,ident='lifetime-'+ident,fault=ProjectFault))
            if not row:
                current,runs=await preview(host,ident)
                if not current['allowed']:raise ProjectFault('This skill is still in use. Stop or finish the listed work before deleting it.',409)
                if data['revision']!=current['revision'] or data['scopeHash']!=current['scopeHash'] or data['confirmName']!=current['name']:
                    raise ProjectFault('The skill or deletion scope changed. Reload and confirm its current name again.',409)
                with db:
                    db.execute('INSERT INTO skill_deletions VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',(rid,ident,fingerprint,current['scopeHash'],data['revision'],'reserved',(root/ident).stat().st_dev,(root/ident).stat().st_ino,encode(runs),now()))
                    db.execute("UPDATE skills SET state='deleting' WHERE id=?",(ident,))
                row=db.execute('SELECT * FROM skill_deletions WHERE request_id=?',(rid,)).fetchone()
            return receipt(row)

def remove(path):
    if path.is_symlink():path.unlink()
    elif path.is_dir():shutil.rmtree(path)
    elif path.exists():path.unlink()


async def finish(host,db,root,row):
    ident=row['skill_id'];rid=row['request_id'];source=root/ident
    stage=packages.folder(root/'.deleting',True)/rid
    selected=source if source.exists() else stage
    if selected.exists():
        if selected.is_symlink() or selected.resolve(strict=True)!=selected or (selected.stat().st_dev,selected.stat().st_ino)!=(row['device'],row['inode']):
            raise ProjectFault('The original skill directory identity changed. Existing data was preserved.',503)
    elif row['phase']=='reserved':raise ProjectFault('The original skill directory could not be confirmed.',503)
    if row['phase']=='staged' and source.exists():raise ProjectFault('The original skill directory unexpectedly reappeared. Existing data was preserved.',503)
    if row['phase']=='reserved':
        if source.exists():
            preserve_pending(host.config['projects'],source/'Sessions/Sessions.sqlite')
            if stage.exists():raise ProjectFault('The skill deletion staging path is already occupied.',503)
            os.rename(source,stage);packages.sync(root);packages.sync(stage.parent)
        with db:db.execute("UPDATE skill_deletions SET phase='staged' WHERE request_id=?",(rid,))
    # A minimal durable user tombstone prevents automatic builtin resurrection.
    retired=packages.folder(root/'.deleted',True)
    packages.atomic(retired/(ident+'.json'),(encode({'id':ident,'deleted':True})+'\n').encode())
    await asyncio.to_thread(remove,stage);packages.sync(stage.parent)
    for run_id in json.loads(row['runs']):
        target=host.root/identity(run_id)
        if (target/'worker.json').exists():
            meta=host.metadata(target/'worker.json')
            if binding(meta)!=('skill',ident):raise ProjectFault('A worker record belongs to another owner.',503)
            remove(target)
    prune_preferences(root,ident)
    with db:
        db.execute('PRAGMA secure_delete=ON')
        db.execute('DELETE FROM saves WHERE skill_id=?',(ident,));db.execute('DELETE FROM revisions WHERE skill_id=?',(ident,));db.execute('DELETE FROM skills WHERE id=?',(ident,))
        if has(db,'builtin_packages'):db.execute('DELETE FROM builtin_packages WHERE skill_id=?',(ident,))
        db.execute("UPDATE skill_deletions SET phase='deleted' WHERE request_id=?",(rid,))
    return original(db,rid,ident)


def prune_preferences(root,ident):
    path=root/'SessionSettings.sqlite'
    if not path.exists():return
    if path.resolve(strict=True)!=path:raise ProjectFault('Skill preference storage is linked.',503)
    with closing(sqlite3.connect(path,timeout=2)) as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=1:raise ProjectFault('Skill preference storage needs maintenance.',503)
        with db:
            db.execute("DELETE FROM overrides WHERE owner_type='skill' AND owner_id=?",(ident,))
            for row in db.execute('SELECT owner_type,owner_id,session_id,choices FROM overrides').fetchall():
                choices=json.loads(row[3])
                if ident in choices:
                    choices.pop(ident)
                    db.execute('UPDATE overrides SET choices=? WHERE owner_type=? AND owner_id=? AND session_id=?',(encode(choices),*row[:3]))

async def resume(host,rid):
    root=skills_root(host.config['projects'])
    with closing(packages.connect(root)) as db:
        row=db.execute('SELECT * FROM skill_deletions WHERE request_id=?',(rid,)).fetchone()
        if not row or row['phase']=='deleted':return
        try:
            with ExitStack() as locks:
                locks.enter_context(lifecycle.lock(root,True,ident=row['skill_id'],fault=ProjectFault))
                locks.enter_context(lifecycle.lock(root,True,ident='lifetime-'+row['skill_id'],fault=ProjectFault))
                with db:db.execute('UPDATE skill_deletions SET error=NULL WHERE request_id=?',(rid,))
                await finish(host,db,root,row)
        except BaseException as error:
            with db:db.execute('UPDATE skill_deletions SET error=? WHERE request_id=?',('Cleanup was not confirmed. Read the original receipt or retry this same request.',rid))
            if isinstance(error,asyncio.CancelledError):raise
