#!/usr/bin/env python3
"""Fixed active-run sidecar: pass the inherited lease, then wait for its original Git receipt."""
import json
import os
from pathlib import Path
import socket
import struct
import sys
import time
import uuid
from common import ProjectFault, document, project_id
from agent import AgentLease, process


def rpc(value, descriptor=None):
    raw = (json.dumps(value) + '\n').encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15); client.connect('/run/r4os-studio-git/control.sock')
        if descriptor is not None:
            written = client.sendmsg([raw], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack('i', descriptor))])
            if written < len(raw): client.sendall(raw[written:])
        else: client.sendall(raw)
        data = b''
        while b'\n' not in data:
            part = client.recv(65536)
            if not part or len(data) + len(part) > 2 * 1024**2: raise ProjectFault('Git broker receipt was lost.', 503)
            data += part
    result = json.loads(data)
    if result.get('error'): raise ProjectFault(result['error'], result.get('code', 503))
    return result['result']


def main():
    os.umask(0o077)
    if len(sys.argv) != 6: raise ProjectFault('Invalid project Git broker invocation.', 400)
    projects, identity, session, run, descriptor = Path(sys.argv[1]).absolute(), project_id(sys.argv[2]), project_id(sys.argv[3]), project_id(sys.argv[4]), int(sys.argv[5])
    config = document(Path('/etc/r4os-studio-git/config.json'))
    if Path(config['projects']) != projects or config['uid'] != os.getuid(): raise ProjectFault('Project Git storage binding changed.', 403)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072: raise ProjectFault('Project push arguments exceeded their limit.', 400)
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) - {'callId', 'commitMessage', 'files'} or not isinstance(data.get('callId'), str): raise ProjectFault('Invalid project push arguments.', 400)
    parent = os.getppid()
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect((projects / identity / 'Sessions/Sessions.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT r.config FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND s.id=? AND s.project_id=?', (run, session, identity)).fetchone()
    if not row: raise ProjectFault('Active project Git run not found.', 403)
    frozen = json.loads(row[0])
    lease = {'sessionId': session, 'runId': run, 'workerPid': parent, 'workerBirth': process(parent)[1], 'revision': frozen['revision'], 'callId': data['callId']}
    AgentLease(config, identity, lease, descriptor).verify()
    request_id = str(uuid.uuid5(uuid.UUID(run), 'github:' + data['callId']))
    value = rpc({'operation': 'agent_submit', 'requestId': request_id, 'projectId': identity, 'kind': 'push', 'agent': lease, 'input': {k: v for k, v in data.items() if k != 'callId'}}, descriptor)
    deadline = time.monotonic() + 330
    while value['state'] in ('queued', 'running'):
        if time.monotonic() > deadline: raise ProjectFault('The original project push remains unconfirmed.', 503)
        time.sleep(.5); value = rpc({'operation': 'job', 'projectId': identity, 'requestId': request_id})
    print(json.dumps({'result': value}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Project push could not be confirmed. Inspect the original Git job; it was not repeated.', 'code': 503})); sys.exit(1)
