"""Managed browser arguments survive REA's deliberate child-env sanitization."""
import json
import os
from pathlib import Path
import sys


def main():
    path=Path('/runner/browser.json')
    with path.open('rb') as stream:
        raw=stream.read(65537)
    if len(raw)>65536:raise RuntimeError('Invalid managed browser configuration size.')
    value=json.loads(raw)
    executable=value['executable']
    if (value.get('schema')!=1 or not isinstance(executable,str) or not executable.startswith('/runtime/')
            or '..' in Path(executable).parts):raise RuntimeError('Invalid managed browser executable.')
    environment={name:text for name,text in value['environment'].items() if name in
        ('PATH','HOME','XDG_CACHE_HOME','LANG','LD_LIBRARY_PATH','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy')}
    arguments=[executable,'--no-sandbox']
    if value.get('proxy'):
        if value['proxy']!='http://127.0.0.1:3128':raise RuntimeError('Invalid private browser proxy.')
        arguments+=['--proxy-server='+value['proxy']]
    os.execve(executable,[*arguments,*sys.argv[1:]],environment)


if __name__=='__main__':main()
