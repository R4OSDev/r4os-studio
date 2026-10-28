"""An idle broker may adopt only the root-owned compatible immutable release."""
import json
from pathlib import Path
import stat

BASE = Path('/opt/r4os-studio/releases')

def candidate(current=Path('/opt/r4os-studio/current'), base=BASE):
    release = current.resolve(strict=True)
    if not release.is_relative_to(base) or release == base: raise ValueError('Invalid remote release root.')
    for path in (release, release / 'release.json', release / 'shared/remote-host.json', release / 'shared/version.json', release / 'scripts/remote-hosts/host.py'):
        info = path.lstat()
        if path.resolve(strict=True) != path or info.st_uid != 0 or info.st_mode & 0o022 or not (stat.S_ISREG(info.st_mode) or path == release and stat.S_ISDIR(info.st_mode)):
            raise ValueError('The remote release is not immutable root-owned source.')
    metadata = json.loads((release / 'release.json').read_text())
    if metadata['id'] != release.name or metadata['version'] != json.loads((release / 'shared/version.json').read_text())['version']:
        raise ValueError('The remote release identity changed.')
    protocol = json.loads((release / 'shared/remote-host.json').read_text())
    if protocol.get('hostProtocol') != 1 or protocol.get('catalogSchema') != 1 or protocol.get('jobSchema', 1) != 1:
        raise ValueError('Remote host maintenance is required for this release.')
    return release / 'scripts/remote-hosts/host.py'


def prepare(host, source):
    if host.active or host.commands.active: return False
    host.accepting = False
    return True
