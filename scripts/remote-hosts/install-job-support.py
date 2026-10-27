#!/usr/bin/env python3
"""Explicit additive private project job path; no bootstrap/unit replacement."""
import json
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run explicit local remote-job setup as root.')
    config = json.loads(Path('/etc/r4os-studio-remote/config.json').read_text())
    projects = Path(config['directory']).parent / 'Projects'
    if projects.resolve(strict=True) != projects: raise SystemExit('The configured Projects directory must be real.')
    parent = Path('/etc/systemd/system/r4os-studio-remote.service.d'); parent.mkdir(mode=0o755, exist_ok=True)
    if parent.resolve(strict=True) != parent: raise SystemExit('Invalid remote support drop-in directory.')
    target = parent / '65-project-jobs.conf'
    quoted = str(projects).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    value = '[Service]\nReadWritePaths="' + quoted + '"\n'
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.read_text() != value: raise SystemExit('Preserve the existing remote-job override for explicit maintenance.')
    else:
        with target.open('x') as stream: stream.write(value); stream.flush(); os.fsync(stream.fileno())
        target.chmod(0o644)
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    print('Private remote project job support prepared. Adopt only the compatible installed release when idle.')


if __name__ == '__main__': main()
