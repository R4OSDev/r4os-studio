#!/usr/bin/env python3
"""Trusted worker sidecar. Socket and fd arguments never come from model input."""
import json
from datetime import datetime, timezone
import os
import socket
import struct
import sys
import time


def rpc(value, descriptor):
    frame = json.dumps(value, ensure_ascii=True).encode() + b'\n'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15); client.connect(sys.argv[1])
        sent = client.sendmsg([frame], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack('i', descriptor))])
        if sent < len(frame): client.sendall(frame[sent:])
        result = b''
        while b'\n' not in result:
            part = client.recv(65536)
            if not part or len(result) + len(part) > 260000: raise ValueError()
            result += part
    return json.loads(result)


def main():
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768: raise ValueError()
    value = json.loads(raw); descriptor = int(sys.argv[2]); os.fstat(descriptor)
    try: response = rpc(value, descriptor)
    except (OSError, ValueError): response = {'error': 'The admission reply was lost. Inspect the original request.', 'code': 503}
    if '--wait' in sys.argv[3:] and value.get('operation') == 'tool' and value.get('tool') in ('run_remote_command', 'remote_files'):
        observer = {**value, 'operation': 'observe'}
        if response.get('code', 0) >= 500:
            try: response = rpc(observer, descriptor)
            except (OSError, ValueError): pass
        job = response.get('result', {})
        deadline = datetime.fromisoformat(job['deadlineAt']).timestamp() if job.get('deadlineAt') else 0
        previous = None
        while job.get('state') in ('queued', 'starting', 'running', 'stopping') and datetime.now(timezone.utc).timestamp() < deadline:
            if '--stream' in sys.argv[3:] and job != previous:
                print(json.dumps({'progress': job}, ensure_ascii=True), flush=True); previous = job
            time.sleep(.25)
            observed = rpc(observer, descriptor)
            if 'error' in observed:
                response = {'result': job, 'observationUnconfirmed': True}; break
            response = observed; job = response.get('result', {})
    print(json.dumps(response, ensure_ascii=True))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'error': 'The remote request receipt was lost. Reconcile the original request; do not repeat the command.', 'code': 503})); sys.exit(1)
