"""Independent optional image purposes in the existing global Settings.sqlite."""
from contextlib import closing
import hashlib
import importlib
import json
import os
import sqlite3
from system_prompt import location
from session_store import identity, encode
from api_model_info import model_id
from store import ProjectFault

PURPOSES = {
    'vision': ('global_fallback','vision','fallback_requests','vision_targets'),
    'image-generation': ('global_image_fallback','imageGeneration','image_fallback_requests','image_targets'),
}

def contract(purpose):
    if purpose not in PURPOSES: raise ProjectFault('Unknown Fallback purpose.',400)
    return PURPOSES[purpose]

def selection(value):
    if value is None: return None
    if not isinstance(value,dict) or set(value) != {'providerId','modelId'}: raise ProjectFault('Invalid Fallback selection.',400)
    return {'providerId':identity(value['providerId']),'modelId':model_id(value['modelId'])}

def current(db,purpose='vision'):
    table,field,_,_=contract(purpose)
    empty={'revision':0,field:None}
    if db is None:return empty
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version==0 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():return empty
    if version!=1:raise ProjectFault('Global settings unavailable.',503)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():return empty
    row=db.execute('SELECT revision,'+field+' FROM '+table+' WHERE id=1').fetchone()
    if row is None:return empty
    if type(row[0]) is not int or not 1<=row[0]<=9007199254740991:raise ProjectFault('Global Fallback settings unavailable.',503)
    return {'revision':row[0],field:selection(json.loads(row[1]))}

def read(projects,purpose='vision'):
    contract(purpose);path=location(projects)
    if not path.exists():return current(None,purpose)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:return current(db,purpose)

def present(projects,providers,purpose='vision'):
    _,field,_,module=contract(purpose);value=read(projects,purpose)
    choices=importlib.import_module(module).listing(providers)
    chosen=value[field];state='Not configured';why=None
    if chosen:
        provider=next((p for p in choices if p['id']==chosen['providerId']),None)
        model=next((m for m in provider['models'] if m['id']==chosen['modelId']),None) if provider else None
        state='Configured' if model and model['available'] else 'Unavailable'
        if state=='Unavailable':why=model['reason'] if model else 'The saved connection or model is unavailable. Its identity was retained.'
    return {**value,'state':state,'reason':why,'providers':choices}

def receipt(projects,rid,purpose='vision'):
    _,_,requests,_=contract(purpose);rid=identity(rid);path=location(projects)
    if path.exists():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(requests,)).fetchone():
                row=db.execute('SELECT result FROM '+requests+' WHERE id=?',(rid,)).fetchone()
                if row:return json.loads(row[0])
    raise ProjectFault('Original Fallback request not found.',404)

def update(projects,providers,data,purpose='vision'):
    table,field,requests,module=contract(purpose)
    if (not isinstance(data,dict) or set(data)!={'requestId','revision',field}
            or type(data['revision']) is not int or not 0<=data['revision']<9007199254740991):
        raise ProjectFault('Invalid Fallback settings.',400)
    rid=identity(data['requestId']);chosen=selection(data[field]);fingerprint=hashlib.sha256(encode(data).encode()).hexdigest()
    try:old_receipt=receipt(projects,rid,purpose)
    except ProjectFault as error:
        if error.code!=404:raise
        old_receipt=None
    freeze=importlib.import_module(module).freeze
    if old_receipt is None and chosen:freeze(providers,chosen)
    if data['revision']!=read(projects,purpose)['revision'] and old_receipt is None:
        raise ProjectFault('Fallback settings changed. Reload before saving.',409)
    path=location(projects,create=True)
    with closing(sqlite3.connect(path,timeout=5)) as db:
        os.chmod(path,0o600);db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version==0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():raise ProjectFault('Unrecognized global settings.',503)
            db.execute('CREATE TABLE system_prompt(id INTEGER PRIMARY KEY CHECK(id=1),prompt TEXT,revision INTEGER NOT NULL)')
            db.execute('PRAGMA user_version=1')
        elif version!=1 or not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_prompt'").fetchone():
            raise ProjectFault('Unsupported global settings.',503)
        db.execute('CREATE TABLE IF NOT EXISTS '+table+'(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,'+field+' TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS '+requests+'(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
        old=db.execute('SELECT fingerprint,result FROM '+requests+' WHERE id=?',(rid,)).fetchone()
        if old:
            if old[0]!=fingerprint:raise ProjectFault('This request belongs to different Fallback settings.',409)
            return json.loads(old[1])
        value=current(db,purpose)
        if data['revision']!=value['revision']:raise ProjectFault('Fallback settings changed. Reload before saving.',409)
        if chosen:freeze(providers,chosen)
        revision=value['revision']+(chosen!=value[field] or value['revision']==0)
        result={'requestId':rid,'revision':revision,field:chosen}
        db.execute('INSERT INTO '+table+' VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,'+field+'=excluded.'+field,(revision,encode(chosen)))
        db.execute('INSERT INTO '+requests+' VALUES(?,?,?)',(rid,fingerprint,encode(result)))
        db.commit();return result
