"""Idle original-host checks shared by explicit SDK maintenance."""
import json
import socket
import subprocess
from store import ProjectFault


def require_idle_hosts(projects, root, inventory):
    for unit in ('r4os-studio-agents.service', 'r4os-studio-development.service'):
        subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=True)
    from clear_cache import worker_admission
    for item in inventory:
        worker_admission(projects, item['id'], {'agents': True, 'development': True}, 'retiring obsolete SDK sources')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(15); client.connect('/run/r4os-studio-components/control.sock')
        client.sendall(b'{"command":"status"}\n'); raw = b''
        while b'\n' not in raw:
            block = client.recv(65536)
            if not block or len(raw) + len(block) > 4 * 1024**2:
                raise ProjectFault('The original component host status could not be confirmed.', 503)
            raw += block
    response = json.loads(raw.split(b'\n')[0])
    if response.get('error') or (response['status'].get('job') or {}).get('phase') == 'working':
        raise ProjectFault('Wait for the original component operation to finish.', 409)
