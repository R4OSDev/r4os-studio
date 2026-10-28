"""Reconcile original local receipts only. Never starts native processes or repeats effects."""
import hashlib
import json
import os
from pathlib import Path
import re
from generated_images import GeneratedImages,RPC_IMAGE_LIMIT
from profile import regular,CODEX_SHA256,CODEX_VERSION
from run_store import item
from session_store import encode
from store import ProjectFault


def reconcile(store,sid,run_id=None,finalizing=False):
    session=store.row(sid);thread=session['thread_id']
    if not finalizing and store.db.execute('SELECT 1 FROM runs WHERE session_id=? AND busy=1 LIMIT 1',(sid,)).fetchone():return
    if not thread:
        reconcile_imports(store,sid,run_id);return
    rows=store.db.execute('SELECT * FROM runs WHERE session_id=?'+(' AND id=?' if run_id else ''),(sid,run_id) if run_id else (sid,)).fetchall()
    allowed={}
    for row in rows:
        config=json.loads(row['config']);engine=config.get('engine',{})
        if config.get('nativeImageGeneration') is not True or engine.get('sha256')!=CODEX_SHA256 or engine.get('version')!=CODEX_VERSION:continue
        if row['turn_id']:allowed[row['turn_id']]=row['id']
        if config.get('goalExecution') and store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_turns'").fetchone():
            for turn in store.db.execute('SELECT turn_id FROM goal_turns WHERE run_id=?',(row['id'],)):allowed[turn[0]]=row['id']
    images=GeneratedImages(store,sid)
    if allowed:
        count=total=0
        for name in ('native','archived'):
            root=store.directory/sid/'Codex'/name
            if not root.exists():continue
            if root.resolve(strict=True)!=root:raise ProjectFault('Unexpected native image history path.',409)
            for parent,children,files in os.walk(root,followlinks=False):
                if len(children)>128:raise ProjectFault('Native image history exceeds its directory bound.',413)
                for child in children:
                    if (Path(parent)/child).is_symlink():raise ProjectFault('Native history contains an unexpected link.',409)
                for filename in files:
                    if not filename.endswith('.jsonl'):continue
                    count+=1
                    if count>128:raise ProjectFault('Native image history exceeds its file bound.',413)
                    path=regular(Path(parent)/filename);info=path.stat();total+=info.st_size
                    if info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>64*1024*1024 or total>128*1024*1024:raise ProjectFault('Native image history exceeds the bounded readback limit.',413)
                    with path.open('rb') as stream:
                        first_line=stream.readline(RPC_IMAGE_LIMIT+1)
                        if len(first_line)>RPC_IMAGE_LIMIT:raise ProjectFault('Native session metadata exceeds its readback bound.',413)
                        first=json.loads(first_line)
                        meta=first.get('payload',{})
                        if first.get('type')!='session_meta' or meta.get('id')!=thread or meta.get('cli_version')!=CODEX_VERSION:continue
                        while line:=stream.readline(RPC_IMAGE_LIMIT+1):
                            if len(line)>RPC_IMAGE_LIMIT:raise ProjectFault('A native image receipt exceeds the readback frame limit. Original history was preserved.',413)
                            try:value=json.loads(line)
                            except ValueError:break  # Preserve a partial final native record.
                            event=value.get('payload',{});native=event.get('item',{})
                            if (value.get('type')!='event_msg' or event.get('type')!='item_completed' or event.get('thread_id')!=thread
                                    or event.get('turn_id') not in allowed or native.get('type')!='Extension' or native.get('kind')!='image_gen.generation' or native.get('status')!='completed'):continue
                            rid=allowed[event['turn_id']];ident=native.get('id')
                            old=store.db.execute('SELECT metadata FROM generated_images WHERE session_id=? AND thread_id=? AND item_id=?',(sid,thread,ident)).fetchone() if images.exists() else None
                            if old:
                                # The confirmed original remains authoritative; never overwrite it.
                                from generated_images import public
                                confirmed=public(json.loads(old[0]),sid)
                                images.path(confirmed['id'])
                                if confirmed['runId']!=rid:raise ProjectFault('The original image run binding changed.',409)
                            else:confirmed=images.accept(rid,thread,{key:native.get(key) for key in ('id','status','result','savedPath')})
                            existing=store.db.execute('SELECT payload FROM items WHERE session_id=? AND run_id=? AND item_id=?',(sid,rid,ident)).fetchone()
                            if existing and json.loads(existing[0]).get('generatedImage',{}).get('id')==confirmed['id']:continue
                            item(store,sid,rid,{'id':ident,'runId':rid,'turnId':event['turn_id'],'type':'tool','tool':'image_gen.imagegen','status':'completed','generatedImage':confirmed,
                                'output':encode({'stage':'Generated','image':confirmed,'recovered':True,'note':'Confirmed from the original native completed receipt. No generation was repeated.'})})
    reconcile_imports(store,sid,run_id)


def reconcile_imports(store,sid,run_id=None):
    root=store.directory/sid/'GeneratedImages/Imports'
    if not root.exists():return
    if root.resolve(strict=True)!=root:raise ProjectFault('Unexpected original import receipt path.',409)
    records=list(root.glob('*.json'))
    if len(records)>256:raise ProjectFault('Image import receipts exceed the readback bound.',413)
    for path in records:
        if not re.fullmatch('[a-f0-9]{64}\\.json',path.name):raise ProjectFault('Unexpected image import receipt identity.',409)
        path=regular(path)
        if path.stat().st_size>16384 or path.stat().st_nlink!=1:raise ProjectFault('Invalid original image import receipt.',409)
        record=json.loads(path.read_text())
        if record.get('schema')!=1 or record.get('sessionId')!=sid or record.get('phase')!='published' or run_id and record.get('runId')!=run_id:continue
        rid=record['runId'];asset=record.get('asset',{})
        for tool in store.db.execute("SELECT * FROM tools WHERE run_id=? AND tool='studio_import_generated_image'",(rid,)):
            if tool['result'] and json.loads(tool['result']).get('success') is True:continue
            if hashlib.sha256((rid+':'+tool['call_id']).encode()).hexdigest()+'.json'!=path.name:continue
            row=store.db.execute('SELECT session_id FROM runs WHERE id=?',(rid,)).fetchone()
            if not row or row[0]!=sid:raise ProjectFault('The original import belongs to another session.',409)
            arguments=json.loads(tool['intent']);fingerprint=hashlib.sha256(encode({'tool':'studio_import_generated_image','arguments':arguments}).encode()).hexdigest()
            if fingerprint!=tool['arguments_hash'] or arguments.get('imageId')!=asset.get('imageId') or arguments.get('format')!=asset.get('format') or arguments.get('path','').casefold()!=record.get('path','').casefold():raise ProjectFault('The original import intent differs from its publication receipt.',409)
            from image_import import validate,digest_at,canonical_target
            validate(arguments);target=record['path']
            if target!=canonical_target(store.workspace,target) or asset.get('path')!=target or asset.get('sha256')!=record.get('sha256'):raise ProjectFault('The original imported asset identity changed.',409)
            # Open through no-follow parents, never a free host/native filename.
            fd=os.open(store.workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                for component in target.split('/')[:-1]:
                    child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
                hashed,_=digest_at(fd,target.rsplit('/',1)[-1])
            finally:os.close(fd)
            if hashed!=asset['sha256']:continue  # User edits remain, no replay or rollback.
            result={'success':True,'output':encode({**asset,'recovered':True,'note':'Original published target verified; import was not repeated.'}),'generatedAsset':asset,'files':{target:asset['sha256']}}
            with store.db:store.db.execute('UPDATE tools SET state=?,result=? WHERE run_id=? AND call_id=?',('completed',encode(result),rid,tool['call_id']))
            item(store,sid,rid,{'id':tool['call_id'],'runId':rid,'type':'tool','tool':'studio.import_generated_image','arguments':arguments,'status':'completed','generatedAsset':asset,'files':result['files'],'output':result['output']})
