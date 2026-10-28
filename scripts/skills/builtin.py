"""Fixed shipped knowledge; idempotent publication, preserve every user edit."""
import hashlib
import json
import os
import fcntl
from pathlib import Path
import uuid

BASE=Path(__file__).resolve().parents[2]/'resources/skills'
SOURCE='r4os-update-packages'
STARTER=b'---\nname: new-skill\ndescription: ""\n---\n\n'

def ensure(db,root,node,api,base=BASE):
    manifest_path=base/(SOURCE+'.json');manifest=json.loads(manifest_path.read_text())
    if manifest.get('schema')!=1 or not isinstance(manifest.get('files'),dict):raise api.SkillFault('The shipped update skill manifest is invalid.',503)
    ident=api.identity(manifest['id']);contents={}
    if api.lifecycle.deleted(root,ident) or (root/'.deleted'/('source-'+hashlib.sha256(SOURCE.encode()).hexdigest()+'.json')).exists():return {'installed':False,'deleted':True}
    for rel,expected in manifest['files'].items():
        path=base/SOURCE/api.relative(rel)
        if path.resolve(strict=True)!=path:raise api.SkillFault('The shipped skill resource is linked.',503)
        data,_=api.regular(path)
        if hashlib.sha256(data).hexdigest()!=expected:raise api.SkillFault('The shipped update skill resource hash differs.',503)
        contents[rel]=data
    bundle_hash=hashlib.sha256(api.encode(manifest).encode()).hexdigest()
    locks=api.folder(root/'.locks',True);fd=os.open(locks/'builtin-r4os-updates',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'installed':False,'reason':'Another builtin initialization is active.'}
        with db:db.execute('CREATE TABLE IF NOT EXISTS builtin_packages(source_id TEXT PRIMARY KEY,skill_id TEXT NOT NULL UNIQUE,bundle_hash TEXT,draft_hash TEXT,active_hash TEXT,status TEXT NOT NULL)')
        claim=db.execute('SELECT * FROM builtin_packages WHERE source_id=?',(SOURCE,)).fetchone()
        row=db.execute('SELECT * FROM skills WHERE id=?',(ident,)).fetchone()
        if row and row['state']=='deleting':return {'installed':False,'deleting':True}
        if claim is None:
            if row is not None:return {'installed':False,'preservedUserChanges':True,'reason':'The shipped ID already belongs to a user skill.'}
            with db:db.execute('INSERT INTO builtin_packages VALUES(?,?,NULL,NULL,NULL,?)',(SOURCE,ident,'creating'))
            claim=db.execute('SELECT * FROM builtin_packages WHERE source_id=?',(SOURCE,)).fetchone()
        if claim['skill_id']!=ident:raise api.SkillFault('Builtin source identity changed; preserve its previous catalog.',503)
        if row is None or row['state']=='creating':
            api.create(db,root,{'id':ident,'name':manifest['name']})
        # Respect the existing per-skill author/busy lock across the complete replacement.
        with api.locked(root,ident):
            current=api.detail(db,root,ident);files,old,draft_hash=api.inventory(root/ident/'Workspace')
            active=current['skill']['activeHash']
            if claim['status']=='published':
                if draft_hash!=claim['draft_hash'] or active!=claim['active_hash']:
                    return {'installed':True,'skillId':ident,'preservedUserChanges':True,'reason':'User draft or published revision preserved.'}
                if claim['bundle_hash']==bundle_hash:return {'installed':True,'skillId':ident,'changed':False}
            else:
                known=all(rel in contents and (data==contents[rel] or rel=='SKILL.md' and data==STARTER) for rel,data in old.items())
                if not known:return {'installed':False,'skillId':ident,'preservedUserChanges':True,'reason':'Interrupted initialization contains user edits.'}
            workspace=api.folder(root/ident/'Workspace')
            # Only an untouched owned bundle is replaced. User files never reach this branch.
            for item in files:
                if item['path'] not in contents:(workspace/item['path']).unlink()
            for rel,data in contents.items():
                path=workspace/rel;api.folder(path.parent,True);api.atomic(path,data)
            api.sync(workspace)
            prepared=api.detail(db,root,ident)
            class Author:
                active=True
                def verify(self,actual_root,actual_id):
                    if not self.active or actual_root!=root or actual_id!=ident:raise api.SkillFault('Builtin skill lock ended.',409)
            author=Author()
            result=api.publish(db,root,{'id':ident,'revision':prepared['skill']['revision'],
                'draftHash':prepared['draftHash'],'requestId':str(uuid.uuid5(uuid.UUID(ident),bundle_hash+':'+prepared['draftHash']))},node,author=author)
            author.active=False
        if not result.get('saved'):raise api.SkillFault('The shipped skill failed complete validation; its draft is preserved.',503)
        with db:db.execute('UPDATE builtin_packages SET bundle_hash=?,draft_hash=?,active_hash=?,status=? WHERE source_id=?',
            (bundle_hash,result['draftHash'],result['skill']['activeHash'],'published',SOURCE))
        return {'installed':True,'skillId':ident,'changed':True,'activeHash':result['skill']['activeHash'],'bundleHash':bundle_hash}
