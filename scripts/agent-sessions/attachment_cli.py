"""Fixed binary stdin transport, separate from run JSON and SSE frames."""
import json
import os
import sys
from owner import binding
from session_store import SessionStore
from attachment_store import Attachments
from store import ProjectFault


def main():
    os.umask(0o077);raw=sys.stdin.buffer.readline(8193)
    if len(raw)>8192 or not raw.endswith(b'\n'):raise ProjectFault('Invalid attachment header.',400)
    request=json.loads(raw);kind,ident=binding(request)
    store=SessionStore(sys.argv[1],sys.argv[2],ident,kind)
    try:
        attachments=Attachments(store,request['sessionId']);op=request['operation']
        if op=='list':result=attachments.listing()
        elif op=='upload':result=attachments.upload(request['input'],sys.stdin.buffer)
        elif op=='receipt':result=attachments.receipt(request['requestId'])
        elif op=='remove':result=attachments.remove(request['attachmentId'])
        elif op=='preview':result=attachments.preview(request['attachmentId'])
        else:raise ProjectFault('Unsupported attachment operation.',400)
        print(json.dumps({'result':result},ensure_ascii=False))
    finally:store.close()


if __name__=='__main__':
    try:main()
    except ProjectFault as e:print(json.dumps({'error':str(e),'code':e.code}));sys.exit(1)
    except Exception:print(json.dumps({'error':'Attachment storage is unavailable. Existing data was preserved.','code':503}));sys.exit(1)
