"""Binary asset transfer under the original worker lease and open workspace descriptor."""
import asyncio
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from generated_images import GeneratedImages
from profile import directory,regular
from run_store import get_run
from session_store import encode
from store import ProjectFault


def validate(args):
    if not isinstance(args,dict) or set(args)-{'imageId','path','format','expectedTargetHash','options'} or not {'imageId','path','format'}<=set(args):raise ProjectFault('Invalid image import.',400)
    path=args['path'];fmt=args['format'];options=args.get('options',{})
    if (not isinstance(path,str) or len(path.encode())>240 or not re.fullmatch(r'(?i:Assets)/(?:[A-Za-z0-9_-][A-Za-z0-9_. -]{0,100}/)*[A-Za-z0-9_-][A-Za-z0-9_. -]{0,100}',path)
            or any(part in ('.','..') or part.endswith(('.', ' ')) for part in path.split('/'))):raise ProjectFault('Choose a relative regular asset path under Assets/.',400)
    extensions={'original':'.png','png':'.png','ico':'.ico','rgba32':'.rgba'}
    if fmt not in extensions or not path.lower().endswith(extensions[fmt]):raise ProjectFault('Use .png for original/PNG, .ico for bitmap ICO, or .rgba for raw RGBA32.',400)
    if not isinstance(options,dict) or set(options)-{'width','height','fit','background'}:raise ProjectFault('Invalid image transformation options.',400)
    if any(type(options[k]) is not int or not 1<=options[k]<=4096 for k in ('width','height') if k in options) or options.get('fit','contain') not in ('contain','cover') or not isinstance(options.get('background','#00000000'),str) or not re.fullmatch(r'#[a-fA-F0-9]{6}(?:[a-fA-F0-9]{2})?',options.get('background','#00000000')):raise ProjectFault('Use bounded dimensions, contain/cover and a #RRGGBB or #RRGGBBAA background.',400)
    if fmt=='original' and options:raise ProjectFault('An original copy cannot be transformed.',400)
    expected=args.get('expectedTargetHash')
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected)):raise ProjectFault('Supply the exact current target SHA-256 or omit it for create only.',400)
    return path,fmt,options,expected


def check_worker(worker):
    row=get_run(worker.store,worker.run_id)
    if (worker.store.owner_type!='project' or worker.config.get('owner')!={'type':'project','id':worker.store.project_id}
            or worker.config['engine']['profile'] not in ('studio-tools-v11','studio-tools-v12','studio-tools-v13') or not row['busy'] or row['state'] not in ('starting','running')
            or worker.stopping or worker.lease is None or worker.lease.closed):raise ProjectFault('Import needs this project’s active original run and workspace lease.',403)
    if not worker.config['permissions'].get('studio.import_generated_image') or not worker.config['permissions'].get('studio.write_file'):
        raise ProjectFault('Import generated image and Write file permissions are required.',403)
    from owner import lock_path
    held=os.fstat(worker.lease.fileno());path=regular(lock_path(worker.store.projects,'project',worker.store.project_id));info=path.stat()
    if held.st_dev!=info.st_dev or held.st_ino!=info.st_ino:raise ProjectFault('The original project lease changed.',403)
    from project_maintenance import pending_git,pending_update,project
    if pending_git(worker.store.projects,worker.store.project_id) or pending_update(worker.store.projects,worker.store.project_id):raise ProjectFault('Reconcile the original project operation before importing an asset.',409)
    if project(worker.store.projects,worker.store.project_id)['pins']!=worker.config.get('projectPins'):raise ProjectFault('Project pins changed after this run was admitted.',409)


async def prepare(source,stage,fmt,options):
    script=Path(__file__).with_name('image_prepare.py');args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--cap-drop','ALL']
    for root in ('/usr','/lib','/lib64'):
        if Path(root).exists():args+=['--ro-bind',root,root]
    args+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(regular(source)),'/input','--bind',str(stage),'/out','--ro-bind',str(script),'/prepare.py','--clearenv','--setenv','LANG','C.UTF-8','/usr/bin/python3','-I','-B','/prepare.py']
    process=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=4096)
    try:
        output,_=await asyncio.wait_for(process.communicate(encode({'format':fmt,'options':options}).encode()),12)
        if len(output)>4096:raise ValueError()
        meta=json.loads(output)
        if process.returncode or 'error' in meta:raise ProjectFault(meta.get('error','Image preparation failed.'),400)
        path=regular(stage/'prepared');info=path.stat()
        if info.st_nlink!=1 or not 0<info.st_size<=64*1024*1024 or info.st_size!=meta['size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError()
        return meta,path
    finally:
        if process.returncode is None:process.kill();await process.wait()


def digest_at(parent,name):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>64*1024*1024:raise ProjectFault('The asset target must be a regular, unlinked bounded file.',409)
        return hashlib.file_digest(stream,'sha256').hexdigest(),(info.st_dev,info.st_ino)


def exchange(a,an,b,bn,flags):
    function=ctypes.CDLL(None,use_errno=True).renameat2
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];function.restype=ctypes.c_int
    if function(a,os.fsencode(an),b,os.fsencode(bn),flags):
        code=ctypes.get_errno()
        if code==errno.EEXIST:raise ProjectFault('The target appeared concurrently. It was preserved.',409)
        raise OSError(code,os.strerror(code))


def publish(worker,path,prepared,expected,metadata,journal):
    root=os.open(worker.store.workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);parent=os.dup(root);stage=os.open(prepared.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for name in path.split('/')[:-1]:
            try:child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            except FileNotFoundError:
                if not worker.config['permissions'].get('studio.create_directory'):raise ProjectFault('Create directory permission is needed for missing asset folders.',403)
                os.mkdir(name,0o755,dir_fd=parent);os.fsync(parent);child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
        name=path.rsplit('/',1)[-1]
        try:old_hash,old_identity=digest_at(parent,name)
        except FileNotFoundError:old_hash=old_identity=None
        if old_hash!=expected:raise ProjectFault('The asset target changed. Read its current hash before importing.',409)
        # Persist the exact original intent before publishing binary bytes.
        from profile import write_json
        record={'schema':1,'runId':worker.run_id,'sessionId':worker.session_id,'path':path,'expectedTargetHash':expected,'sha256':metadata['sha256'],'oldIdentity':old_identity,'asset':metadata,'phase':'committing'}
        write_json(journal,record)
        check_worker(worker)
        with prepared.open('rb') as stream:os.fsync(stream.fileno())
        exchange(stage,prepared.name,parent,name,1 if expected is None else 2)
        if expected is not None:
            displaced,_=digest_at(stage,prepared.name)
            if displaced!=expected:
                if digest_at(parent,name)[0]==metadata['sha256']:exchange(stage,prepared.name,parent,name,2)
                raise ProjectFault('A concurrent asset change was preserved. Review the original import receipt.',409)
        os.fsync(parent);os.fsync(stage)
        record['phase']='published';write_json(journal,record)
        # The staged previous target is removed only after a confirmed matching exchange.
        if prepared.exists():prepared.unlink()
    finally:os.close(root);os.close(parent);os.close(stage)


def canonical_target(workspace,path):
    root=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);current=os.dup(root);names=path.split('/');result=[]
    try:
        for index,name in enumerate(names):
            entries=os.listdir(current)
            if len(entries)>10000:raise ProjectFault('The asset directory exceeds its entry bound.',413)
            matches=[entry for entry in entries if entry.casefold()==name.casefold()]
            if len(matches)>1:raise ProjectFault('Resolve existing asset names that differ only by case before importing. No folder was merged.',409)
            if not matches:return '/'.join(result+names[index:])
            actual=matches[0];result.append(actual)
            if index<len(names)-1:
                child=os.open(actual,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current);os.close(current);current=child
        return '/'.join(result)
    finally:os.close(current);os.close(root)

async def import_image(worker,args,call_id):
    path,fmt,options,expected=validate(args);check_worker(worker)
    images=GeneratedImages(worker.store,worker.session_id);source=images.path(args['imageId']);original=images.get(args['imageId'])
    if not isinstance(call_id,str) or not 1<=len(call_id)<=256:raise ProjectFault('Invalid original image import call.',400)
    token=hashlib.sha256((worker.run_id+':'+call_id).encode()).hexdigest();base=directory(images.root()/'Imports')
    journal=base/(token+'.json')
    # Normally Worker.tool returns its durable original result. A surviving committing
    # journal is read-only recovery evidence: never blindly write or generate again.
    if journal.exists():raise ProjectFault('This original import has a publication journal. Reconcile its existing target; it was not repeated.',409)
    if len(list(base.iterdir()))>=256:raise ProjectFault('This session reached its import receipt limit.',413)
    used=0
    for parent,dirs,files in os.walk(base,followlinks=False):
        for name in dirs:
            if (Path(parent)/name).is_symlink():raise ProjectFault('Unexpected import storage link.',409)
        for name in files:
            held=regular(Path(parent)/name);info=held.stat();used+=info.st_size
            if info.st_nlink!=1 or used>256*1024*1024:raise ProjectFault('Import storage requires review before another conversion.',413)
    async with worker.terminals.lock:
        async with worker.sandbox.lock:
            if any(not process.finished.is_set() for process in worker.terminals.processes.values()):raise ProjectFault('Finish active terminal processes before importing an image.',409)
            check_worker(worker)
            path=canonical_target(worker.store.workspace,path)
            stage=directory(base/token)
            try:
                meta,prepared=await prepare(source,stage,fmt,options);check_worker(worker)
                meta.update(imageId=original['id'],sourceSha256=original['sha256'],path=path,stage='Imported')
                publish(worker,path,prepared,expected,meta,journal)
            except BaseException:
                if not journal.exists():
                    for entry in stage.iterdir():
                        if entry.is_file() and not entry.is_symlink():entry.unlink()
                    stage.rmdir()
                raise
            stage.rmdir()
    result={**meta,'imageId':original['id'],'sourceSha256':original['sha256'],'path':path,'stage':'Imported','manifestHint':'ICON='+path if fmt=='ico' else 'RESOURCE=IMAGE:'+path,
        'next':'Register ICON or RESOURCE in module.R4MF and update the consuming code using this project’s pinned SDK. Assets alone does not embed a resource. Build and verify the actual R4X resource inventory; guest verification is separate.'}
    return {'success':True,'output':encode(result),'generatedAsset':result,'files':{path:meta['sha256']}}
