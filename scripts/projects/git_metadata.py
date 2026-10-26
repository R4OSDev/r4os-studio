"""Portable source metadata; local identities and credentials never enter a repository."""
import json
from pathlib import Path


def portable(project):
    return {'schema': 1, 'language': project['language'], 'template': project['template'],
            'moduleName': project['moduleName'], 'pins': project['pins']}


def create(directory, project):
    directory = Path(directory); target = directory / '.r4os-studio'
    target.mkdir(mode=0o700, exist_ok=False)
    (target / 'project.json').write_text(json.dumps(portable(project), indent=2) + '\n')
    ignore = directory / '.gitignore'
    existing = ignore.read_text() if ignore.exists() else ''
    patterns = ['/.zig-cache/', '/zig-out/'] if project['language'] in ('Zig', 'C') else ['/target/']
    patterns += ['/.studio/', '!/.r4os-studio/', '!/.r4os-studio/project.json']
    ignore.write_text(existing.rstrip('\n') + '\n\n# R4OS Studio project sources\n' + '\n'.join(patterns) + '\n')
