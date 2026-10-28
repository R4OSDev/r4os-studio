"""Readonly companion documents through existing SDK file-tool arguments."""
import asyncio
import json
from pathlib import Path
import re
from file_worker import parts,Fault
from image_instructions import ALIAS
from profile import regular
from session_store import encode


def target(arguments):
    if arguments.get('root','workspace')!='sdk':return None
    names=parts(arguments.get('path','.'))
    return names[1:] if names and names[0]==ALIAS else None

async def read(worker,name,arguments,relative):
    if worker.store.owner_type!='project':return {'success':False,'error':'unavailable','output':'Image project recipes require a project session.'}
    if name not in ('read_file','list_directory','search'):return {'success':False,'error':'readOnly','output':'Studio image recipes are read-only.'}
    sdk=worker.config.get('projectPins',{}).get('sdk',{}).get('revision')
    if not isinstance(sdk,str) or not re.fullmatch('[a-f0-9]{40}',sdk):return {'success':False,'error':'unavailable','output':'The project SDK binding is unavailable.'}
    original=Path(worker.manifest['r4os'])/'SDK'/sdk/ALIAS
    if original.exists() or original.is_symlink():return {'success':False,'error':'conflict','output':'The selected SDK contains a conflicting companion path. Its files were preserved.'}
    root=Path(__file__).resolve().parents[2]/'shared/r4os/image-recipes'
    if relative and (len(relative)!=1 or relative[0] not in ('README.txt','images.zig','images.h','images.rs')):return {'success':False,'error':'unavailable','output':'Choose a listed readonly image companion file.'}
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--cap-drop','ALL']
    for path in ('/usr','/lib','/lib64'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    args+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(root),'/sdk','--ro-bind',str(regular(Path(__file__).with_name('file_worker.py'))),'/file_worker.py','--chdir','/sdk','--clearenv','--setenv','LANG','C.UTF-8','/usr/bin/python3','-I','-B','/file_worker.py']
    process=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=262144)
    try:
        raw,_=await asyncio.wait_for(process.communicate(encode({'tool':name,'arguments':{**arguments,'root':'sdk','path':'/'.join(relative) or '.'}}).encode()),5)
        if process.returncode or len(raw)>196608:raise ValueError()
        result=json.loads(raw)
        result['companion']={'kind':'studio-image-recipes','sdkRevision':sdk,'contractRevision':worker.config.get('projectPins',{}).get('contract',{}).get('revision'),'readonly':True}
        return result
    finally:
        if process.returncode is None:process.kill();await process.wait()
