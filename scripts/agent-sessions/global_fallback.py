"""One optional vision selection in the existing global Settings.sqlite."""
from contextlib import closing
import hashlib
import json
import os
import sqlite3
from system_prompt import location
from session_store import identity, encode
from api_model_info import model_id
from store import ProjectFault


def selection(value):
    if value is None: return None
    if not isinstance(value,dict) or set(value) != {'providerId','modelId'}: raise ProjectFault('Invalid Vision selection.',400)
    return {'providerId':identity(value['providerId']),'modelId':model_id(value['modelId'])}


def current(db):
    if db is None: return {'revision':0,'vision':None}
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 0 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone(): return {'revision':0,'vision':None}
    if version != 1: raise ProjectFault('Global settings unavailable.',503)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='global_fallback'").fetchone(): return {'revision':0,'vision':None}
    row = db.execute('SELECT revision,vision FROM global_fallback WHERE id=1').fetchone()
    if row is None: return {'revision':0,'vision':None}
    if type(row[0]) is not int or not 1 <= row[0] <= 9007199254740991: raise ProjectFault('Global Fallback settings unavailable.',503)
    return {'revision':row[0],'vision':selection(json.loads(row[1]))}


def read(projects):
    path = location(projects)
    if not path.exists(): return current(None)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db: return current(db)


def present(projects,providers):
    value = read(projects)
    from vision_targets import listing
    choices = listing(providers)
    selected = value['vision']; state = 'Not configured'; why = None
    if selected:
        provider = next((p for p in choices if p['id']==selected['providerId']),None)
        model = next((m for m in provider['models'] if m['id']==selected['modelId']),None) if provider else None
        state = 'Configured' if model and model['available'] else 'Unavailable'
        if state == 'Unavailable': why = model['reason'] if model else 'The saved connection or model is unavailable. Its identity was retained.'
    return {**value,'state':state,'reason':why,'providers':choices}


def receipt(projects,rid):
    rid = identity(rid); path = location(projects)
    if path.exists():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fallback_requests'").fetchone():
                row = db.execute('SELECT result FROM fallback_requests WHERE id=?',(rid,)).fetchone()
                if row: return json.loads(row[0])
    raise ProjectFault('Original Fallback request not found.',404)


def update(projects,providers,data):
    if (not isinstance(data,dict) or set(data) != {'requestId','revision','vision'}
            or type(data['revision']) is not int or not 0 <= data['revision'] < 9007199254740991):
        raise ProjectFault('Invalid Fallback settings.',400)
    rid = identity(data['requestId']); chosen = selection(data['vision']); fingerprint = hashlib.sha256(encode(data).encode()).hexdigest()
    # Validate a new selection before creating a first settings database. An
    # original receipt remains readable even after its provider disconnects.
    try:
        old_receipt = receipt(projects,rid)
    except ProjectFault as error:
        if error.code != 404: raise
        old_receipt = None
    if old_receipt is None and chosen:
        from vision_targets import freeze
        freeze(providers,chosen)
    if data['revision'] != read(projects)['revision'] and old_receipt is None:
        raise ProjectFault('Fallback settings changed. Reload before saving.',409)
    path = location(projects,create=True)
    with closing(sqlite3.connect(path,timeout=5)) as db:
        os.chmod(path,0o600); db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone(): raise ProjectFault('Unrecognized global settings.',503)
            db.execute('CREATE TABLE system_prompt(id INTEGER PRIMARY KEY CHECK(id=1),prompt TEXT,revision INTEGER NOT NULL)')
            db.execute('PRAGMA user_version=1')
        elif version != 1 or not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_prompt'").fetchone():
            raise ProjectFault('Unsupported global settings.',503)
        db.execute('CREATE TABLE IF NOT EXISTS global_fallback(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,vision TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS fallback_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
        old = db.execute('SELECT fingerprint,result FROM fallback_requests WHERE id=?',(rid,)).fetchone()
        if old:
            if old[0] != fingerprint: raise ProjectFault('This request belongs to different Fallback settings.',409)
            return json.loads(old[1])
        value = current(db)
        if data['revision'] != value['revision']: raise ProjectFault('Fallback settings changed. Reload before saving.',409)
        if chosen:
            from vision_targets import freeze
            freeze(providers,chosen)
        revision = value['revision'] + (chosen != value['vision'] or value['revision'] == 0)
        result = {'requestId':rid,'revision':revision,'vision':chosen}
        db.execute('INSERT INTO global_fallback VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,vision=excluded.vision',(revision,encode(chosen)))
        db.execute('INSERT INTO fallback_requests VALUES(?,?,?)',(rid,fingerprint,encode(result)))
        db.commit(); return result
