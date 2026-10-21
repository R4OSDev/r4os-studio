"""Small versioned Studio contracts, independent of the native R4OS ABI."""
import hashlib
import json
from pathlib import Path
import re
import uuid

APP = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((APP / 'shared/development-host.json').read_text())
LIMITS = CONTRACT['limits']
TOOLS = ('build_project', 'deploy_project', 'run_project', 'read_development_job',
         'stop_development_job', 'capture_vm', 'send_vm_input')
ACTIVE = ('queued', 'starting', 'running', 'stopping')
TERMINAL = ('completed', 'failed', 'interrupted', 'unknown')


class DevelopmentFault(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


class UnconfirmedGuestEffect(DevelopmentFault):
    """A command may have reached the guest; never replay it automatically."""
    uncertain = True


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise DevelopmentFault('Invalid development identity.', 400)
    return str(uuid.UUID(value))


def encode(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def hash_value(value): return hashlib.sha256(encode(value).encode()).hexdigest()


def generation(value):
    # Native process generations are u64. Never round them through JSON numbers.
    if not isinstance(value, str) or not re.fullmatch('[1-9][0-9]{0,19}', value) or int(value) > 18446744073709551615:
        raise DevelopmentFault('Invalid guest process generation.', 400)
    return value


def relative(value, allow_dot=False):
    if allow_dot and value == '.': return value
    if not isinstance(value, str) or not value or len(value.encode()) > 1024:
        raise DevelopmentFault('Invalid development file name.', 400)
    if value.startswith('/') or '\\' in value or ':' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DevelopmentFault('Use a relative project file name.', 400)
    if any(part in ('', '.', '..') for part in value.split('/')):
        raise DevelopmentFault('Use a relative project file name.', 400)
    return value


def protocol(root):
    try: value = json.loads((Path(root) / 'shared/development-host.json').read_text())
    except (OSError, ValueError): raise DevelopmentFault('This Studio release has no compatible development worker.', 503)
    keys = ('schema', 'interface', 'hostProtocol', 'workerProtocol', 'dataSchema', 'guestProtocol')
    if any(value.get(key) != CONTRACT[key] for key in keys):
        raise DevelopmentFault('Development host maintenance is required.', 503)
    return {key: value[key] for key in keys}
