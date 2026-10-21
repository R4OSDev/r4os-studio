#!/usr/bin/env python3
"""Explicit local build of one registered Rust project using its immutable Studio pins."""
import argparse
import json
import os
from pathlib import Path
import re
from store import connect, operation
from sdk import profile
from rust_projects import build

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('project_id')
args = parser.parse_args()
if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', args.project_id):
    parser.error('Use the immutable project UUID.')
os.umask(0o077)
root = Path(os.environ.get('STUDIO_R4OS_DIR') or Path(__file__).resolve().parents[2] / 'Data/R4OS').resolve()
projects = root.parent / 'Projects'
with connect(projects) as db:
    project = operation(db, {'operation': 'get', 'id': args.project_id}, root)
if project['language'] != 'Rust' or 'rust' not in project['pins']:
    parser.error('The selected project has no verified Rust profile.')
context = profile(root, projects, project['pins'])
print(build(context, projects / args.project_id))
