"""Render a lifecycle unit from the VM worker's resource settings."""

import re

from contracts import LIMITS


def render(vm_worker):
    if ('ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py %i\n' not in vm_worker
            or 'ExecStopPost=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py %i --finalize\n' not in vm_worker):
        raise ValueError('The original VM worker dispatcher differs.')
    # Leave time for timeout handling after the application deadline.
    maximum = LIMITS['vmLifecycleTimeoutSeconds'] + 60
    text, matches = re.subn(r'^RuntimeMaxSec=[^\n]*$', f'RuntimeMaxSec={maximum}', vm_worker, flags=re.M)
    if matches != 1 or '\nDescription=R4OS Studio VM development job %i\n' not in text:
        raise ValueError('The original VM worker unit differs.')
    return text.replace('Description=R4OS Studio VM development job %i',
                        'Description=R4OS Studio VM lifecycle job %i', 1)
