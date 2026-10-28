#!/usr/bin/env python3
"""Explicit local decoder installation; never called by the web app/updater."""
import json
import os
import subprocess
import sys
import hashlib
from pathlib import Path
import tempfile


def agent_guard():
    if os.getuid()!=0:raise SystemExit('Installing the fixed agent guard requires the local root installer.')
    target=Path('/opt/r4os-studio/bin/agent-launch.py');source=Path(__file__).parent/'agent-sessions/launch.py'
    before=hashlib.sha256(target.read_bytes()).hexdigest();after=hashlib.sha256(source.read_bytes()).hexdigest()
    if (target.resolve(strict=True)!=target or target.stat().st_uid!=0 or target.stat().st_mode & 0o022
            or before not in ('a8018450d089973be5ed775f92ca497b9ba51b5d30428b8626b9db8da67bb962',
                '3f85922d6623138b7540e4a240347ca0bbfaa318a385c82373b2c49de84de3e6',after)):
        raise SystemExit('The existing dispatcher differs from the qualified binding. Preserve and review it.')
    fd,temp=tempfile.mkstemp(prefix='.agent-guard-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(source.read_bytes());os.fchmod(stream.fileno(),0o755);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,target)
        directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if Path(temp).exists():Path(temp).unlink()
    print(json.dumps({'agentDispatcherBefore':before,'agentDispatcherAfter':after,'serviceRestart':False,'workerOrVmRestart':False,'projectAndProviderDataChanged':False}))


def main():
    if '--agent-guard' in sys.argv:return agent_guard()
    if '--check' not in sys.argv:
        if os.getuid()!=0:raise SystemExit('Run the explicit local installer as root, or use --check.')
        packages=['python3-pil=11.1.0-5+deb13u4']
        if '--pdf' in sys.argv:packages.append('poppler-utils=25.03.0-5+deb13u4')
        subprocess.run(['/usr/bin/apt-get','--assume-yes','--no-install-recommends','install',*packages],check=True)
    from PIL import Image,features,__version__
    if __version__!='11.1.0' or not features.check('webp'):raise SystemExit('The qualified Pillow11.1.0/WebP decoder is unavailable.')
    import io
    for kind in ('PNG','JPEG','WEBP'):
        buf=io.BytesIO();Image.new('RGB',(2,2),'purple').save(buf,kind);buf.seek(0)
        with Image.open(buf,formats=[kind]) as image:image.load();assert image.size==(2,2)
    result={'pillow':__version__,'formats':['PNG','JPEG','WEBP'],'projectAndProviderDataChanged':False,'serviceRestart':False}
    if '--pdf' in sys.argv:
        version=subprocess.run(['/usr/bin/pdftotext','-v'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        if b'pdftotext version 25.03.0' not in version.stderr:raise SystemExit('The qualified Poppler25.03.0 PDF extractor is unavailable.')
        result['pdfText']='Poppler25.03.0'
    print(json.dumps(result))


if __name__=='__main__':main()
