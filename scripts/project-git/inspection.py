"""Scoped immutable Git previews/selections; never commit, fetch, pull or push."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from common import ProjectFault, storage, folder, source_path, document, digest, save, now, project_id

LIMITS = {'selectionFiles':512,'selectionPathBytes':65536,'sourceFiles':10000,
    'sourceBytes':268435456,'fileBytes':33554432,'pathBytes':1024,
    'pageEntries':25,'pageBytes':12288,'diffCaptureBytes':131072,'diffPageTextBytes':6000,
    'previewDocuments':8192,'previewBytes':268435456}


def sha(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ProjectFault('Use the original immutable snapshot/selection identifier.',400)
    return value


def push_input(value):
    if not isinstance(value,dict) or set(value) != {'selectionId','commitMessage'}:
        raise ProjectFault('Push requires an explicit selectionId and commit description.',400)
    sha(value['selectionId']);message=value['commitMessage']
    if not isinstance(message,str) or not message.strip() or len(message.encode())>4000 or '\x00' in message:
        raise ProjectFault('Enter a commit description of1..4000 UTF-8 bytes.',400)


def binding_key(value):
    if not value: return None
    return {**{k:value[k] for k in ('revision','connectionId','userId','branch')},
        'repository':{k:value['repository'][k] for k in ('id','owner','name')}}


def store_document(base,value):
    identity=digest(value);path=base/(identity+'.json')
    if path.exists(): return load_document(base,identity,value['kind'])
    if len(json.dumps(value,ensure_ascii=False).encode())>16*1024**2:
        raise ProjectFault('The bounded Git preview metadata exceeds16MiB.',409)
    result={**value,'id':identity,'createdAt':now()};save_preview(path,result)
    return result


def save_preview(path,value):
    count=0;total=len(json.dumps(value,ensure_ascii=False).encode())+1
    for entry in path.parent.iterdir():
        info=entry.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise ProjectFault('The original private Git preview store is inconsistent.',409)
        count+=1;total+=info.st_size
        if count>=8192 or total>268435456:
            raise ProjectFault('The private Git preview store reached8192 documents/256MiB. Original evidence was retained.',409)
    save(path,value)


def load_document(base,identity,kind):
    path=base/(sha(identity)+'.json')
    if not path.exists() and not path.is_symlink():raise ProjectFault('The original Git preview/selection is unavailable.',404)
    value=document(path,16*1024**2)
    original={k:v for k,v in value.items() if k not in ('id','createdAt')}
    if value.get('id') != identity or value.get('kind') != kind or digest(original) != identity:
        raise ProjectFault('The original immutable Git preview is inconsistent.',409)
    return value


def owned(value,project,agent):
    if (value.get('projectId') != project or value.get('sessionId') != agent.value['sessionId']
            or value.get('runId') != agent.value['runId']):
        raise ProjectFault('This Git preview belongs to another project, session or original run.',403)


@contextmanager
def operation(config,project,agent):
    from operations import Operations
    base=storage(config['projects'],project)
    parent=base/'Temp';parent.mkdir(mode=0o700,exist_ok=True);folder(parent)
    with tempfile.TemporaryDirectory(prefix='inspection-',dir=parent) as temporary:
        if not (base/'Repo/HEAD').is_file():raise ProjectFault('Initialize and bind the project repository before reading its sources.',409)
        action=Operations(config,{'projectId':project},read_only=True,temporary=temporary)
        expected=agent.frozen.get('githubBinding')
        if not isinstance(expected,dict) or binding_key(action.bound) != expected:
            raise ProjectFault('The repository or branch differs from this run’s frozen binding.',409)
        if action.git.text('symbolic-ref','--short','HEAD') != expected['branch']:
            raise ProjectFault('The actual local branch differs from the frozen repository binding.',409)
        yield action


def capture(action,agent):
    state=action.status();entries=[]
    for change in state['changes']:
        path=source_path(change['path']);file=action.source.get(path)
        entries.append({**change,'sha256':file['sha256'] if file else None,
            'bytes':file['size'] if file else 0,'executable':file['executable'] if file else None,
            **({'previousPath':action.renames[path]} if path in action.renames else {})})
    if action.git.head() != state['head']:
        raise ProjectFault('The original Git base changed during inspection. Read a fresh snapshot.',409)
    return {'schema':1,'kind':'snapshot','projectId':action.id,'sessionId':agent.value['sessionId'],
        'runId':agent.value['runId'],'binding':binding_key(action.bound),'head':state['head'],
        'sourceSnapshot':state['snapshot'],'changesHash':digest(state['changes']),'entries':entries,
        'sourceFiles':len(action.source),'sourceBytes':sum(f['size'] for f in action.source.values())}


def current(action,value,agent):
    owned(value,action.id,agent)
    if value.get('binding') != binding_key(action.bound):
        raise ProjectFault('The original repository/branch binding changed. Review a new selection.',409)
    state=action.status()
    if (state['head'] != value.get('head') or state['snapshot'] != value.get('sourceSnapshot')
            or digest(state['changes']) != value.get('changesHash') or action.git.head() != state['head']):
        raise ProjectFault('The original base, file states or bytes changed. Review a fresh snapshot/selection.',409)
    return state


def page(value,query):
    start=query.get('offset',0);limit=query.get('limit',25);entries=value['entries']
    if type(start) is not int or not 0<=start<=len(entries) or type(limit) is not int or not 1<=limit<=25:
        raise ProjectFault('Use the original Git page cursor and1..25 entries.',400)
    rows=[]
    for entry in entries[start:start+limit]:
        if rows and len(json.dumps([*rows,entry],ensure_ascii=False).encode())>7500:break
        rows.append(entry)
    next_offset=start+len(rows)
    return {'readOnly':True,'immutableSnapshot':True,'snapshotId':value.get('snapshotId',value['id']),
        **({'selectionId':value['id']} if value['kind']=='selection' else {}),
        'baseHead':value['head'],'repository':value['binding']['repository'],'branch':value['binding']['branch'],
        'bindingRevision':value['binding']['revision'],'sourceSnapshot':value['sourceSnapshot'],
        'capturedAt':value['createdAt'],'entries':rows,'offset':start,'nextOffset':next_offset,
        'totalEntries':len(entries),'hasMore':next_offset<len(entries),'limits':LIMITS}


def validate_selection(action,agent,identity):
    base=action.base/'Selections'
    if not base.exists():raise ProjectFault('The original explicit Git selection is unavailable.',404)
    folder(base)
    value=load_document(base,identity,'selection');current(action,value,agent)
    paths=value.get('files')
    if (not isinstance(paths,list) or not 1<=len(paths)<=512 or len(set(paths)) != len(paths)
            or sum(len(source_path(p).encode())+1 for p in paths)>65536):
        raise ProjectFault('The original explicit Git selection is invalid.',409)
    if [v['path'] for v in value['entries']] != paths:
        raise ProjectFault('The original Git selection path binding is inconsistent.',409)
    return value


def inspect(config,project,agent,query):
    # Immutable preview publication still serializes per project: its original
    # count/byte admission cannot race another preview after the global state
    # lock is released. Unrelated projects and job reads keep running.
    base=storage(config['projects'],project)
    descriptor=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ProjectFault('Another Git inspection is active for this project. Read again shortly.',409) from None
        return inspect_locked(config,project,agent,query)
    finally:os.close(descriptor)


def inspect_locked(config,project,agent,query):
    if not isinstance(query,dict):raise ProjectFault('Use a declared Git inspection view.',400)
    view=query.get('view')
    allowed={'status':{'snapshotId','offset','limit'},'diff':{'snapshotId','path','offset'},
        'select':{'snapshotId','files'},'selection':{'selectionId','offset','limit'},'job':{'requestId'}}
    if view not in allowed or set(query)-({'view'}|allowed[view]):raise ProjectFault('Unexpected Git inspection fields.',400)
    if view=='job':
        identity=project_id(query.get('requestId'))
        value=document(folder(Path(config['projects'])/'.studio/github/Jobs'/identity)/'job.json')
        if value.get('id') != identity or value.get('projectId') != project or (value.get('agent') or {}).get('sessionId') != agent.value['sessionId']:
            raise ProjectFault('This original Git job belongs to another project/session.',403)
        result=value.get('result') or {}
        return {'readOnly':True,'job':{k:value[k] for k in ('id','projectId','kind','state','phase','createdAt','updatedAt','code') if k in value},
            'result':{k:result[k] for k in ('commit','remoteHead','pushed','committed','nothingToPush','notPublished','localCommitOnly') if k in result},
            'originalEffectUnknown':value.get('state')=='unknown','replayed':False}
    base=storage(config['projects'],project)/'Selections';base.mkdir(mode=0o700,exist_ok=True);folder(base)
    if view=='selection':
        value=load_document(base,query.get('selectionId'),'selection');owned(value,project,agent)
        return page(value,query)
    with operation(config,project,agent) as action:
        if view=='status':
            if 'snapshotId' in query:
                value=load_document(base,query['snapshotId'],'snapshot');owned(value,project,agent)
            else:
                if query.get('offset',0) != 0:raise ProjectFault('Continue status with its original snapshotId.',400)
                value=store_document(base,capture(action,agent))
            return page(value,query)
        value=load_document(base,query.get('snapshotId'),'snapshot');owned(value,project,agent)
        if view=='select':
            current(action,value,agent);files=query.get('files');changes={v['path']:v for v in value['entries']}
            if (not isinstance(files,list) or not 1<=len(files)<=512 or any(not isinstance(f,str) for f in files)
                    or len(set(files)) != len(files) or sum(len(source_path(f).encode())+1 for f in files)>65536):
                raise ProjectFault('Select1..512 explicit changed paths with at most65536 UTF-8 path bytes.',400)
            if any(path not in changes for path in files):raise ProjectFault('Select only reviewed paths in this original snapshot.',409)
            for entry in value['entries']:
                if entry.get('previousPath') and ((entry['path'] in files) != (entry['previousPath'] in files)):
                    raise ProjectFault('Select both old and new paths of an observed rename.',400)
            data={k:v for k,v in value.items() if k not in ('id','createdAt','entries')}
            data.update(kind='selection',snapshotId=value['id'],files=files,entries=[changes[f] for f in files])
            selected=store_document(base,data)
            return {**page(selected,{}),'selectionReady':True,'selectedFiles':len(files),
                'notice':'Review this explicit immutable selection; Push permission and commit description remain required. Admission rechecks all original bindings.'}
        path=source_path(query.get('path'));cache=base/(digest({'snapshotId':value['id'],'path':path})+'.diff.json')
        if cache.exists():
            preview=document(cache,2*1024**2)
            if preview.get('snapshotId') != value['id'] or preview.get('path') != path:
                raise ProjectFault('The original diff binding is inconsistent.',409)
        else:
            current(action,value,agent)
            preview=action.diff({'path':path,'snapshot':value['sourceSnapshot']})['diff']
            raw=preview['text'].encode();capture_bytes=raw[:131072].decode('utf8',errors='ignore').encode()
            preview.update(text=capture_bytes.decode(),captureTruncated=preview['truncated'] or len(raw)>len(capture_bytes),
                snapshotId=value['id'],sha256=hashlib.sha256(capture_bytes).hexdigest());save_preview(cache,preview)
        raw=preview['text'].encode();offset=query.get('offset',0)
        if hashlib.sha256(raw).hexdigest() != preview.get('sha256'):
            raise ProjectFault('The immutable original diff hash is inconsistent.',409)
        if type(offset) is not int or not 0<=offset<=len(raw):raise ProjectFault('Use the original diff nextOffset in UTF-8 bytes.',400)
        try:text=raw[offset:offset+6000].decode('utf8',errors='strict')
        except UnicodeDecodeError:
            try:text=raw[offset:].decode('utf8')[:1500]
            except UnicodeDecodeError:raise ProjectFault('Continue diff from its exact original nextOffset.',400) from None
        while len(json.dumps(text,ensure_ascii=False).encode())>6000:text=text[:max(1,len(text)*3//4)]
        end=offset+len(text.encode())
        return {'readOnly':True,'immutableSnapshot':True,'snapshotId':value['id'],'baseHead':value['head'],'path':path,
            'text':text,'offset':offset,'nextOffset':end,'totalBytes':len(raw),'hasMore':end<len(raw),
            'captureTruncated':preview['captureTruncated'],'binary':preview['binary'],'sha256':preview['sha256'],'limits':LIMITS}
