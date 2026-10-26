"""A fixed dispatcher capability, qualified through explicit administrator maintenance."""
import hashlib
import json
from pathlib import Path
import stat

LAUNCHER = Path('/opt/r4os-studio/bin/development-launch.py')
MARKER = Path('/etc/r4os-studio-development/package-support.json')


def available():
    try:
        for path in (LAUNCHER, MARKER):
            info = path.lstat()
            if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 131072: return False
        value = json.loads(MARKER.read_text())
        return value == {'schema': 1, 'packageJobs': 1, 'launcherSha256': hashlib.sha256(LAUNCHER.read_bytes()).hexdigest()}
    except (OSError, ValueError, TypeError): return False


def extend(text):
    old = "name = 'worker.py' if meta.get('kind', 'build') == 'build' else 'vm_worker.py'"
    new = "name = 'worker.py' if meta.get('kind', 'build') in ('build', 'package') else 'vm_worker.py'"
    if text.count(new) == 1 and old not in text: return text
    if text.count(old) != 1: raise ValueError('The existing development dispatcher needs individual review; it was preserved.')
    return text.replace(old, new)
