#!/usr/bin/env python3
"""Install the reviewed SDK-retirement updater guard; preserve existing host setup."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

OLD_SHA = '033f4726958efc46a94fc6ef3b2fd226c9bf8ca3865a5d31171a4c750b429ad6'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('This narrow updater compatibility maintenance requires root.')
    target = Path('/opt/r4os-studio/bin/update-host.py')
    source = Path(__file__).with_name('host.py')
    before, after = target.read_bytes(), source.read_bytes()
    ast.parse(after)
    if before == after:
        print('SDK retirement compatibility is already installed.'); return
    if hashlib.sha256(before).hexdigest() != OLD_SHA:
        raise SystemExit('The original updater changed. Review its current bytes before maintenance.')
    status = Path('/var/lib/r4os-studio-updates/status.json')
    if status.exists() and json.loads(status.read_text()).get('phase') in ('checking','downloading','building','activating','recovering'):
        raise SystemExit('Wait for the original updater operation to finish.')
    if Path('/var/lib/r4os-studio-updates/transaction.json').exists():
        raise SystemExit('Reconcile the original updater transaction before maintenance.')
    evidence = args.evidence_dir.absolute(); evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    if evidence.resolve(strict=True) != evidence:
        raise SystemExit('The evidence directory is indirect.')
    backup = evidence / 'update-host-before-sdk-retirement.py'
    if backup.exists() and backup.read_bytes() != before:
        raise SystemExit('The original updater evidence already belongs to different bytes.')
    if not backup.exists(): backup.write_bytes(before); backup.chmod(0o600)
    subprocess.run(['systemctl','stop','r4os-studio-updates.service'], check=True)
    temporary = target.with_name('.update-host-sdk-profiles.tmp')
    with temporary.open('wb') as stream:
        os.fchmod(stream.fileno(), 0o755); stream.write(after); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(target)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    subprocess.run(['systemctl','start','r4os-studio-updates.service'], check=True)
    receipt = {'oldSha256': OLD_SHA, 'newSha256': hashlib.sha256(after).hexdigest(), 'sdkRetirementGuard': True}
    (evidence / 'updater-sdk-compatibility.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('SDK retirement compatibility installed. Existing Studio, workers and VMs preserved.')


if __name__ == '__main__': main()
