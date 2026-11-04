"""Bounded official artifact downloads and safe private Node extraction."""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tarfile
import urllib.request
from urllib.parse import urlsplit
import uuid


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        old, new = urlsplit(request.full_url), urlsplit(newurl)
        if new.scheme!='https' or new.hostname!=old.hostname or new.username or new.password:
            raise ValueError('The artifact redirect leaves its official HTTPS origin.')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def file_hash(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or path.resolve(strict=True)!=path:
        raise ValueError('The artifact cache is linked or not a regular private file.')
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def download(api,url,path,maximum,expected=None):
    api.folder(path.parent,True)
    lock=path.with_name('.'+path.name+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        if path.exists():
            if path.stat().st_size>maximum or expected and file_hash(path)!=expected:
                raise api.SkillFault('The existing official artifact cache differs. Its original bytes were preserved.',503)
            file_hash(path)
            return path
        temporary=path.with_name('.download-'+str(uuid.uuid4()))
        request=urllib.request.Request(url,headers={'User-Agent':'R4OS-Studio-managed-skill-runtime'})
        client=urllib.request.build_opener(Redirects())
        try:
            with client.open(request,timeout=60) as response,temporary.open('xb') as output:
                if response.status!=200:raise ValueError('Official artifact download did not return200.')
                total=0
                while block:=response.read(1024*1024):
                    total+=len(block)
                    if total>maximum:raise ValueError('Official artifact exceeds its explicit byte limit.')
                    output.write(block)
                output.flush();os.fsync(output.fileno())
            if expected and file_hash(temporary)!=expected:raise ValueError('The official artifact SHA256 differs.')
            os.rename(temporary,path);api.sync(path.parent)
        except Exception:
            # Preserve an incomplete original under its unambiguous private staging name.
            raise
    return path


def node_plan(api,skills,source):
    value=api.regular(source/'.nvmrc')[0].decode().strip()
    if not re.fullmatch('v?[0-9]+[.][0-9]+[.][0-9]+',value):
        raise api.SkillFault('REA must declare one exact supported source-build Node version in .nvmrc.',409)
    version='v'+value.removeprefix('v')
    architecture={'x86_64':'x64','aarch64':'arm64'}.get(platform.machine())
    if platform.system()!='Linux' or architecture is None:
        raise api.SkillFault('This managed REA recipe requires a supported Linux Node distribution.',409)
    name='node-'+version+'-linux-'+architecture+'.tar.xz'
    cache=api.folder(skills/'.downloads/node'/version,True)
    base='https://nodejs.org/dist/'+version+'/'
    sums=download(api,base+'SHASUMS256.txt',cache/'SHASUMS256.txt',1024*1024)
    rows=[line.split() for line in sums.read_text().splitlines()]
    values=[row[0] for row in rows if len(row)==2 and row[1]==name]
    if len(values)!=1 or not re.fullmatch('[a-f0-9]{64}',values[0]):
        raise api.SkillFault('The pinned Node distribution has no unique official SHA256.',503)
    return dict(version=version,architecture=architecture,name=name,url=base+name,sha256=values[0],
                checksumManifestHash=file_hash(sums),cache=str(cache/name))


def install_node(api,plan,target):
    archive=download(api,plan['url'],Path(plan['cache']),128*1024*1024,plan['sha256'])
    temporary=api.folder(target.parent/'Node-unpack',True)
    if any(temporary.iterdir()):raise api.SkillFault('The original Node extraction staging is not empty.',409)
    with tarfile.open(archive,'r:xz') as tar:
        members=tar.getmembers()
        if len(members)>20000 or sum(item.size for item in members)>768*1024*1024:
            raise api.SkillFault('The Node archive exceeds its extraction limits.',409)
        for item in members:
            path=PurePosixPath(item.name)
            if path.is_absolute() or any(part in ('..','.') for part in path.parts) or not (item.isfile() or item.isdir() or item.issym()):
                raise api.SkillFault('The Node archive contains an unsupported path or entry.',409)
        tar.extractall(temporary,filter='data')
    roots=list(temporary.iterdir())
    if len(roots)!=1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise api.SkillFault('The official Node archive has an unexpected root.',503)
    for path in roots[0].rglob('*'):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(roots[0]):
            raise api.SkillFault('A Node runtime link leaves its private installation.',409)
    os.rename(roots[0],target);temporary.rmdir();api.sync(target.parent)
    return dict(path='Node/bin/node',sha256=file_hash(target/'bin/node'),version=plan['version'],
                origin={k:plan[k] for k in ('url','sha256','checksumManifestHash','architecture')})
