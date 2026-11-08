"""Freeze assigned-VM metadata through its coordinator, through the assigned owner binding."""
import json
import os
import re
import socket
import time


def request(project_id):
    deadline = time.monotonic() + 3
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(3)
        stream.connect(os.environ.get('STUDIO_DEVELOPMENT_SOCKET', '/run/r4os-studio-development/host.sock'))
        stream.settimeout(max(.001, deadline - time.monotonic()))
        stream.sendall((json.dumps({'operation': 'project_vm_context', 'projectId': project_id}) + '\n').encode())
        data = bytearray()
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or len(data) >= 2048: raise ValueError()
            stream.settimeout(remaining)
            chunk = stream.recv(2049 - len(data))
            if not chunk: raise ValueError()
            data.extend(chunk)
        if len(data) > 2048: raise ValueError()
        return json.loads(data)['result']


def snapshot(store):
    project = store.project
    ident = project.get('vmId')
    value = {'version': 1, 'projectRevision': project['revision'], 'vmId': ident, 'available': False}
    if not ident:
        return {**value, 'reason': 'No VM was assigned when this input was accepted.'}
    try:
        if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise ValueError()
        context = request(project['id'])
        if (set(context) != set(value) | {'vmRevision', 'imageId', 'imageSha256'}
                or type(context['version']) is not int or context['version'] != 1
                or type(context['projectRevision']) is not int or context['projectRevision'] != project['revision']
                or context['vmId'] != ident or context['available'] is not True
                or not re.fullmatch('[a-f0-9]{64}', context['imageSha256'])
                or any(not isinstance(context[key], str) or not 1 <= len(context[key]) <= 128 for key in ('vmRevision', 'imageId'))):
            raise ValueError()
        return context
    except (OSError, ValueError, KeyError, TypeError):
        return {**value, 'reason': 'The assigned VM identity was unavailable when this input was accepted.'}
