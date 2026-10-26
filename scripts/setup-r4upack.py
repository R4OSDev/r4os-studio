#!/usr/bin/env python3
"""Explicit minimal setup, using pinned existing Zig; never changes active defaults."""
import argparse
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'components'))
from r4upack import install

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path(os.environ.get('STUDIO_R4OS_DIR', Path(__file__).resolve().parents[1] / 'Data/R4OS')))
parser.add_argument('--source-dir', type=Path, help='Administrator-provided repository/path tree; every file is checked against fixed hashes.')
args = parser.parse_args()
if os.geteuid() == 0: parser.error('Run as the unprivileged data owner, e.g. runuser -u r4os-studio -- python3 App/scripts/setup-r4upack.py')
os.umask(0o077)
class Setup:
    root = args.root.absolute()
    def progress(self, message): print(message, flush=True)
value = install(Setup(), args.source_dir)
print('Qualified R4UPack: ' + value['id'] + '\nBinary SHA-256: ' + value['sha256'] + '\nChoose this profile separately in System → Updates → Tools → R4UPack.')
