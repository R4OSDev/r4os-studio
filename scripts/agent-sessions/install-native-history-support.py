#!/usr/bin/env python3
"""Targeted host maintenance for growing native history; no service restarts."""
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run native-history host maintenance as root.')
    unit = 'r4os-studio-agent@.service'
    installed = Path('/etc/systemd/system') / unit
    text = installed.read_text()
    expected = ('ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/agent-launch.py %i',
                'ExecStopPost=/usr/bin/python3 -B /opt/r4os-studio/bin/agent-launch.py %i --finalize',
                'User=r4os-studio')
    if installed.is_symlink() or any(line not in text.splitlines() for line in expected):
        raise SystemExit('Review the existing agent unit before native-history maintenance.')
    path = installed.with_name(unit + '.d') / '73-native-history.conf'
    wanted = '[Service]\nLimitFSIZE=268435456:infinity\n'
    if path.is_symlink() or (path.exists() and path.read_text() != wanted):
        raise SystemExit('Review the existing native-history override before maintenance.')
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix('.tmp')
        with temporary.open('x') as stream:
            stream.write(wanted); stream.flush(); os.fsync(stream.fileno())
        temporary.chmod(0o644); temporary.replace(path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Native-history support installed for future agent workers; no services, runs or VMs restarted.')


if __name__ == '__main__': main()
