"""Cross-process VM reservation shared by development and manual management."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

from contracts import DevelopmentFault, encode, identity
from jobs import folder, now
from layout import save

class VmBusy(DevelopmentFault): pass


def birth(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


class VmLease:
    def __init__(self, projects, vm_id, scope):
        self.root = folder(Path(projects) / '.studio/development'); self.vm_id = identity(vm_id)
        self.id = str(uuid.uuid4()); self.token = secrets.token_hex(32); self.scope = scope; self.stream = None

    def __enter__(self):
        path = folder(self.root / 'vm-locks') / (self.vm_id + '.lock')
        if path.is_symlink(): raise DevelopmentFault('Invalid VM reservation file.', 503)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600); self.stream = os.fdopen(fd, 'a')
        try: fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close(); self.stream = None
            raise VmBusy('This VM is reserved by another operation. Stop its development job before controlling it.', 409)
        self.value = {'schema': 1, 'id': self.id, 'token': self.token, 'vmId': self.vm_id,
            'pid': os.getpid(), 'birth': birth(os.getpid()), 'scope': self.scope,
            'createdAt': now(), 'closedAt': None}
        save(folder(self.root / 'leases') / (self.id + '.json'), self.value)
        return self

    def __exit__(self, *args):
        if self.stream:
            try:
                if self.scope.get('kind') == 'manual': (self.root / 'leases' / (self.id + '.json')).unlink(missing_ok=True)
                else:
                    self.value['closedAt'] = now(); save(self.root / 'leases' / (self.id + '.json'), self.value)
            finally: self.stream.close(); self.stream = None


def inspect(projects, lease_id, token=None, check_boot=True):
    root = Path(projects) / '.studio/development'; path = root / 'leases' / (identity(lease_id) + '.json')
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid VM reservation.', 403)
    value = json.loads(path.read_text())
    if value['id'] != lease_id or value['schema'] != 1 or value['closedAt'] or (token is not None and not secrets.compare_digest(value['token'], token)):
        raise DevelopmentFault('The VM reservation is no longer active.', 409)
    try:
        if birth(value['pid']) != value['birth']: raise ValueError()
    except (OSError, ValueError): raise DevelopmentFault('The VM reservation owner is no longer running.', 409)
    if check_boot and value['scope'].get('bootId'):
        path = root / 'Boots' / (identity(value['vmId']) + '.json')
        try:
            if path.resolve(strict=True) != path: raise ValueError()
            boot = json.loads(path.read_text())
            if (not boot['connected'] or boot['bootId'] != value['scope']['bootId']
                or boot['vmRevision'] != value['scope']['vmRevision'] or birth(boot['pid']) != boot['birth']): raise ValueError()
        except (OSError, ValueError, KeyError): raise DevelopmentFault('The guest boot binding changed or its observer was lost.', 409)
    lock = root / 'vm-locks' / (identity(value['vmId']) + '.lock')
    if lock.resolve(strict=True) != lock: raise DevelopmentFault('Invalid VM reservation file.', 503)
    with lock.open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return value
    raise DevelopmentFault('The VM reservation lock is no longer held.', 409)


def main():
    os.umask(0o077)
    op, projects = sys.argv[1], Path(sys.argv[2]).resolve()
    # Legacy VM-only installs and isolated test data have no development host.
    config = Path('/etc/r4os-studio-development/config.json')
    installed = config.is_file() and Path(json.loads(config.read_text())['projects']) == projects
    if op == 'manual':
        if not installed:
            print(encode({'locked': True, 'developmentHost': False}), flush=True); sys.stdin.buffer.read(1); return
        with VmLease(projects, sys.argv[3], {'kind': 'manual'}):
            print(encode({'locked': True, 'developmentHost': True}), flush=True); sys.stdin.buffer.read(1)
    elif op == 'inspect':
        request = json.loads(sys.stdin.buffer.read(8193)); value = inspect(projects, request['leaseId'], request['token'], request.get('checkBoot', True))
        # A private bridge needs the bound scope, never a reusable credential.
        value.pop('token'); print(encode({'result': value}))
    else: raise DevelopmentFault('Unsupported VM reservation operation.', 400)


if __name__ == '__main__':
    try: main()
    except DevelopmentFault as error: print(encode({'error': str(error), 'code': error.code}), flush=True); sys.exit(1)
    except Exception: print('{"error":"VM reservation support is unavailable.","code":503}', flush=True); sys.exit(1)
