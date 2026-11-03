#!/usr/bin/env python3
"""Prepare a complete SDK through Studio's regular component host."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
import uuid

def request(value):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(15)
        client.connect('/run/r4os-studio-components/control.sock')
        client.sendall((json.dumps(value) + '\n').encode())
        raw = b''
        while b'\n' not in raw:
            block = client.recv(65536)
            if not block or len(raw) + len(block) > 4 * 1024**2:
                raise ValueError('The original component response could not be confirmed.')
            raw += block
    result = json.loads(raw.split(b'\n')[0])
    if result.get('error'):
        raise ValueError(result['error'])
    return result['status']


def wait_original():
    while True:
        status = request({'command': 'status'})
        job = status.get('job') or {}
        if job.get('phase') != 'working':
            if job.get('error') or job.get('phase') == 'failed':
                raise ValueError(job.get('error') or 'The original SDK preparation failed.')
            return status
        time.sleep(.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-id', help='An exact SDK revision from the official component catalog; default: latest stable.')
    args = parser.parse_args()
    status = request({'command': 'status'})
    if status.get('features', {}).get('sdkProfiles') != 1:
        raise ValueError('Install current SDK profile component-host support first. No legacy setup is available.')
    if (status.get('job') or {}).get('phase') == 'working':
        raise ValueError('An original component operation is running. Observe it before a new setup request.')
    request({'command': 'check', 'kind': 'sdk'})
    status = wait_original()
    component = status['components']['sdk']
    ident = args.sdk_id or component['latestId']
    selected = next((item for item in component['available'] + component['installed'] if item['id'] == ident), None)
    if selected is None:
        raise ValueError('Select an exact SDK revision from the current official catalog.')
    original = {'command': 'download', 'kind': 'sdk', 'id': ident, 'requestId': str(uuid.uuid4()),
                'expectedProfileRevision': status['profileRevision']}
    print(json.dumps({'sdkId': ident, 'requestId': original['requestId'], 'action': 'download'}), flush=True)
    # If submission loses its response, only observe the durable original.
    try:
        request(original)
    except (OSError, TimeoutError):
        print('Submission response lost; observing the original request. No second download was submitted.', flush=True)
    status = wait_original()
    job = status.get('job') or {}
    if job.get('requestId') != original['requestId'] or job.get('phase') != 'complete':
        raise ValueError('The original SDK preparation is unconfirmed. Inspect its request ID in System updates.')
    print('Complete SDK package and SDK-owned host tools prepared. Activate through explicit SDK migration or System updates.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('SDK setup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
