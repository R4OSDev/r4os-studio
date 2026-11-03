"""Portable source metadata; local identities and credentials never enter a repository."""
import json
from pathlib import Path
import stat


def ensure_exfiles(directory):
    directory = Path(directory)
    external = directory / 'ExFiles'
    if external.is_symlink():
        raise ValueError('ExFiles must be a local project directory.')
    external.mkdir(mode=0o700, exist_ok=True)
    ignore = directory / '.gitignore'
    if ignore.exists() or ignore.is_symlink():
        info = ignore.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('The project .gitignore must be a regular local file.')
        existing = ignore.read_bytes()
    else:
        existing = b''
    if b'/ExFiles/' not in existing.splitlines():
        newline = b'\r\n' if b'\r\n' in existing else b'\n'
        with ignore.open('ab') as stream:
            if existing and not existing.endswith(b'\n'):
                stream.write(newline)
            stream.write(newline + b'# Local external files; never publish their contents.' + newline + b'/ExFiles/' + newline)


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
    ensure_exfiles(directory)
