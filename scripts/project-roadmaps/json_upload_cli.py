#!/usr/bin/env python3
"""Fixed binary upload adapter: JSON header then at most 16 MiB original bytes."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'projects'))
from store import ProjectFault
from storage import connection
from validation import fields,integer,identity
from json_contract import MAX_BYTES
from json_upload import upload

def main():
    os.umask(0o077);line=sys.stdin.buffer.readline(4097)
    if len(line)>4096 or not line.endswith(b'\n'):raise ProjectFault('Invalid JSON upload envelope.',400)
    body=json.loads(line);fields(body,['projectId','fileId','byteLength','sha256']);identity(body['projectId']);identity(body['fileId']);integer(body['byteLength'],1,MAX_BYTES)
    import re
    if not isinstance(body['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',body['sha256']):raise ProjectFault('Invalid original file sha256.',400)
    with connection(Path(sys.argv[1]),body['projectId']) as db:
        if db is None:raise ProjectFault('Initialize this project roadmap before importing JSON.',404)
        raw=sys.stdin.buffer.read(body['byteLength']+1)
        result=upload(db,Path(sys.argv[1]),body['projectId'],body['fileId'],raw,body['sha256'],body['byteLength']);print(json.dumps({'result':result},ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except ProjectFault as e:print(json.dumps({'error':str(e),'code':e.code}));sys.exit(1)
    except Exception:print(json.dumps({'error':'The original JSON upload is unconfirmed. Read its retained file receipt before retrying.','code':503}));sys.exit(1)
