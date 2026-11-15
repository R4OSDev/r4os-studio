#!/usr/bin/env python3
"""Install the lifecycle worker template on an existing Studio host."""

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from projects.development_units import LIFECYCLE_UNIT, VM_UNIT
from lifecycle_unit import render


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run VM lifecycle host maintenance as root.')
    units = Path('/etc/systemd/system')
    source = units / VM_UNIT.format('')
    original = source.lstat()
    if not stat.S_ISREG(original.st_mode) or original.st_uid != 0 or original.st_mode & 0o022:
        raise SystemExit('Invalid existing VM worker unit.')
    text = render(source.read_text())
    target = units / LIFECYCLE_UNIT.format('')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or target.read_text() != text:
            raise SystemExit('The existing lifecycle worker unit differs. Review it before installing.')
    else:
        with tempfile.NamedTemporaryFile(mode='w', dir=units, prefix='.studio-lifecycle-', delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(text)
                output.flush()
                os.fchmod(output.fileno(), 0o644)
                os.fsync(output.fileno())
                os.link(temporary, target)
            finally:
                temporary.unlink()
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    print('Studio VM lifecycle worker is available.')


if __name__ == '__main__':
    main()
