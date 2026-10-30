#!/usr/bin/env python3
"""Explicit unprivileged fixed-profile installation; no login, npm or model run."""
import base64
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from urllib.request import build_opener,HTTPRedirectHandler

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'scripts/agent-sessions'))
from api_provider_store import private
from claude_runtime import profile,verify


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def sync_directory(path):
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def publish(stage,target):
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renameat2;rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    if rename(-100,os.fsencode(stage),-100,os.fsencode(target),1)!=0:
        raise OSError(ctypes.get_errno(),'The runtime target already exists or cannot be published.')


def install(providers,archives=None):
    if os.geteuid()==0:raise RuntimeError('Run this installer as the unprivileged r4os-studio service user or your development user.')
    if platform.system()!='Linux' or platform.machine()!='x86_64' or platform.libc_ver()[0]!='glibc':
        raise RuntimeError('This pinned runtime requires Linux x86_64 with glibc.')
    os.umask(0o077);providers=Path(providers).absolute();private(providers,directory=True)
    root=providers/'ClaudeRuntime';private(root,directory=True,create=True)
    lock=root/'install.lock';private(lock,create=True)
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        expected=profile();target=root/expected['id']
        if target.exists() or target.is_symlink():return verify(target,expected)
        stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=root))
        try:
            for kind in ('sdk','native'):
                pin=expected[kind];url=pin['archiveUrl']
                if not url.startswith('https://registry.npmjs.org/@anthropic-ai/'):raise RuntimeError('Unexpected runtime source.')
                archive=stage/(kind+'.tgz');sha256=hashlib.sha256();sha512=hashlib.sha512();count=0
                cached=Path(archives)/(('SDK' if kind=='sdk' else 'Native')+'-0.3.312.tgz') if archives else None
                if cached and (cached.is_symlink() or not cached.is_file()):raise RuntimeError('Cached runtime archive is not a regular file.')
                source=cached.open('rb') if cached else build_opener(NoRedirect()).open(url,timeout=30)
                with source as response,archive.open('xb') as output:
                    while chunk:=response.read(1024*1024):
                        count+=len(chunk)
                        if count>400*1024*1024:raise RuntimeError('Runtime archive limit exceeded.')
                        sha256.update(chunk);sha512.update(chunk);output.write(chunk)
                    output.flush();os.fsync(output.fileno())
                if (sha256.hexdigest()!=pin['archiveSha256']
                        or 'sha512-'+base64.b64encode(sha512.digest()).decode()!=pin['archiveIntegrity']):
                    raise RuntimeError('Runtime archive integrity mismatch.')
                destination=stage/kind;destination.mkdir(mode=0o700)
                with tarfile.open(archive) as tar:
                    members=tar.getmembers();names=[m.name for m in members]
                    if len(members)!=len(pin['files']) or len(set(names))!=len(names):raise RuntimeError('Unexpected archive members.')
                    for item in members:
                        name=item.name.removeprefix('package/')
                        if not item.isfile() or item.name!='package/'+name or name not in pin['files'] or '/' in name:
                            raise RuntimeError('Runtime archive contains an unsupported path or link.')
                        filepin=pin['files'][name]
                        if item.size!=filepin['bytes']:raise RuntimeError('Runtime member size mismatch.')
                        path=destination/name
                        with tar.extractfile(item) as source,path.open('xb') as output:
                            shutil.copyfileobj(source,output,1024*1024);output.flush();os.fsync(output.fileno())
                        path.chmod(0o700 if filepin.get('executable') else 0o600)
                archive.unlink()
            manifest=stage/'profile.json'
            with manifest.open('x') as output:
                output.write(json.dumps(expected,indent=2)+'\n');output.flush();os.fsync(output.fileno())
            manifest.chmod(0o600);verify(stage,expected)
            for path in (stage/'sdk',stage/'native',stage):sync_directory(path)
            # An already installed profile is never replaced or silently fixed.
            publish(stage,target);sync_directory(root)
            return verify(target,expected)
        finally:
            if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,help='Read already downloaded archives; all pinned hashes/integrity checks still apply.')
    options=parser.parse_args()
    data=Path(os.environ.get('STUDIO_DATA_DIR',str(APP/'Data')))
    result=install(data/'LLMProvider',options.archives)
    print(json.dumps({'installedProfile':result['id'],'nativeVersion':result['version'],'sdkVersion':result['sdkVersion'],
        'modelTurnsQualified':result['qualified']['modelTurns'],'login':False,'modelInference':False}))
