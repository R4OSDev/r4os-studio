#!/usr/bin/env python3
"""Keep each VM on one immutable release through ExecStopPost, across updates."""
import json
import os
from pathlib import Path
import re
import sys

BASE = Path('/opt/r4os-studio')


def main():
    if len(sys.argv) not in {2, 3} or (len(sys.argv) == 3 and sys.argv[2] != '--sync'):
        raise RuntimeError('Invalid VM worker invocation.')
    identity = sys.argv[1]
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', identity):
        raise RuntimeError('Invalid VM identity.')
    config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    pin = Path('/run/r4os-studio-vms') / identity / 'worker.json'
    if len(sys.argv) == 2:
        release = (BASE / 'current').resolve()
        temporary = pin.with_suffix('.tmp')
        temporary.write_text(json.dumps({'release': str(release)}))
        os.replace(temporary, pin)
    else:
        release = Path(json.loads(pin.read_text())['release']).resolve()
    if not release.is_relative_to(BASE / 'releases') or not (release / 'release.json').is_file():
        raise RuntimeError('Invalid pinned worker release.')
    os.execv(config['node'], [config['node'], str(release / 'backend/dist/modules/virtual-machines/runner.js'), *sys.argv[1:]])


if __name__ == '__main__':
    main()
