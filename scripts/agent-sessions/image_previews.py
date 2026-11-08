"""Derived thumbnails in the existing immutable private image store."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from attachment_store import sync
from profile import directory,regular
from store import ProjectFault

MAX_PREVIEW=393216


def descriptor(path,meta):
    path=regular(path);info=path.stat()
    if info.st_nlink != 1 or not 0 < info.st_size <= MAX_PREVIEW:raise ValueError()
    raw=path.read_bytes()
    if len(raw)!=meta['size'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or len(raw)<33:raise ValueError()
    if [int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big')]!=[meta['width'],meta['height']]:raise ValueError()
    if meta['mediaType']!='image/png' or any(type(meta[key]) is not int or not 0<meta[key]<=1024 for key in ('width','height')):raise ValueError()
    return str(path)


def isolated_preview(path):
    script=Path(__file__).with_name('image_thumbnail.py').absolute()
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--cap-drop','ALL']
    for root in ('/usr','/lib','/lib64'):
        if Path(root).exists():args+=['--ro-bind',root,root]
    args+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(regular(path)),'/input',
           '--ro-bind',str(script),'/preview.py','--clearenv','--setenv','LANG','C.UTF-8','/usr/bin/python3','-I','-B','/preview.py']
    try:
        completed=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False)
        if completed.returncode or len(completed.stdout)>528384:raise ValueError()
        result=json.loads(completed.stdout)
        if set(result)!={'png','width','height'} or any(type(result[key]) is not int or not 0<result[key]<=1024 for key in ('width','height')):raise ValueError()
        raw=base64.b64decode(result.pop('png'),validate=True)
        if not 0<len(raw)<=MAX_PREVIEW or raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError()
        return raw,result
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired):
        raise ProjectFault('The isolated image preview is unavailable. Original bytes were preserved.',503) from None


def preview(images,ident,create=False):
    original=images.path(ident);image=images.get(ident)
    if image['size']<=MAX_PREVIEW and max(image['width'],image['height'])<=1024:
        return {'path':str(original),'image':image,'preview':{key:image[key] for key in ('size','sha256','mediaType','width','height')}}
    root=images.root()/'Previews';name=ident+'.'+image['sha256'];path=root/(name+'.png');metadata=root/(name+'.json')
    if root.exists() or root.is_symlink():
        directory(root)
        if path.exists() and metadata.exists():
            try:
                entry=regular(metadata);info=entry.stat()
                if info.st_nlink != 1 or info.st_size > 4096:raise ValueError()
                meta=json.loads(entry.read_text())
                if meta['schema']!=1 or meta['sourceSha256']!=image['sha256'] or meta['imageId']!=image['id'] or meta['sessionId']!=images.sid:raise ValueError()
                return {'path':descriptor(path,meta),'image':image,'preview':meta}
            except (OSError,ValueError,TypeError,KeyError):
                raise ProjectFault('The saved image preview needs review. Original bytes were preserved.',409) from None
    if not create:return None
    before=original.stat();raw,facts=isolated_preview(original)
    after=images.path(ident).stat()
    if (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns):
        raise ProjectFault('The original image changed during preview creation.',409)
    from generated_images import MAX_OWNER
    if images.owner_disk_usage()+len(raw)+4096>MAX_OWNER:raise ProjectFault('Private image storage is full. Original bytes were preserved.',413)
    root.mkdir(mode=0o700,exist_ok=True);directory(root);sync(root.parent)
    meta={'schema':1,'imageId':image['id'],'sessionId':images.sid,'sourceSha256':image['sha256'],
          'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mediaType':'image/png',**facts}
    for target,data in ((path,raw),(metadata,json.dumps(meta).encode())):
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=root,prefix=ident+'.',suffix='.pending',delete=False) as output:
                temporary=Path(output.name);output.write(data);output.flush();os.fsync(output.fileno())
            os.replace(temporary,target);sync(root)
        finally:
            if temporary is not None and temporary.exists():temporary.unlink()
    return {'path':descriptor(path,meta),'image':image,'preview':meta}
