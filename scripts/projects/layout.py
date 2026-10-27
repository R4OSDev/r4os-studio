"""Explicit, recoverable source-layout migration; project identity/pins never change."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from store import ProjectFault


def folder(path):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
        raise ProjectFault('Invalid project source directory. All data was preserved.')
    return path


def project_directory(projects, identity):
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', identity):
        raise ProjectFault('Invalid project identity.', 400)
    return folder(folder(projects) / identity)


def workspace(projects, identity, require_current=False):
    project = project_directory(projects, identity)
    current = project / 'Workspace'
    if current.exists() or current.is_symlink():
        folder(current)
        if (project / 'module.R4MF').exists():
            raise ProjectFault('Project layout is ambiguous. All files were preserved.')
        if not (current / 'module.R4MF').is_file():
            raise ProjectFault('The project workspace is incomplete.')
        return current
    if not require_current and (project / 'module.R4MF').is_file():
        return project
    raise ProjectFault('Migrate this project to the Workspace layout before creating sessions.')


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def save(path, data):
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path); sync(path.parent)


def inventory(path):
    result = {}
    for p in sorted(path.rglob('*')):
        mode = p.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ProjectFault('Linked or special project files require manual layout migration.')
        if stat.S_ISREG(mode):
            with p.open('rb') as f: result[str(p.relative_to(path))] = hashlib.file_digest(f, 'sha256').hexdigest()
    return result


def migrate(projects, identity, rollback=False):
    project = project_directory(projects, identity)
    private_roadmap = project / 'Roadmap/Roadmap.sqlite'
    if not (project / 'Workspace').exists() and (private_roadmap.exists() or private_roadmap.is_symlink()):
        raise ProjectFault('This legacy project has private roadmap data. Reconcile its private data before migrating sources; all files were preserved.')
    journals = Path(projects) / '.studio/layouts'
    journals.mkdir(mode=0o700, parents=True, exist_ok=True); folder(journals)
    journal = journals / (identity + '.json')
    target, stage = project / 'Workspace', project / '.workspace-migration'
    if journal.is_symlink(): raise ProjectFault('Invalid layout journal.')
    data = json.loads(journal.read_text()) if journal.exists() else None
    if data and data.get('projectId') != identity: raise ProjectFault('Invalid layout journal identity.')
    if data and data['phase'] == 'rolledBack' and not rollback:
        archive = journals / (identity + '.previous.' + str(__import__('time').time_ns()) + '.json')
        os.rename(journal, archive); sync(journals)
        data = None
    if data is None:
        if target.exists() or target.is_symlink():
            workspace(projects, identity, True)
            return {'layout': 2, 'changed': False}
        if rollback: raise ProjectFault('No layout migration to roll back.')
        if stage.exists() or stage.is_symlink() or (project / 'Sessions').exists():
            raise ProjectFault('Layout destination conflicts with existing data; all files were preserved.')
        if not (project / 'module.R4MF').is_file(): raise ProjectFault('Unrecognized legacy layout.')
        entries = sorted(p.name for p in project.iterdir())
        hashes = inventory(project)
        data = {'schema': 1, 'projectId': identity, 'entries': entries, 'hashes': hashes,
                'phase': 'moving', 'minimumStudio': '0.3.8'}
        save(journal, data)
    if data['phase'] == 'rolledBack': return {'layout': 1, 'changed': False}
    if rollback:
        if data['phase'] == 'rollingBack' and not target.exists() and not stage.exists():
            actual = inventory(project)
            if actual != data['hashes']: raise ProjectFault('Rollback requires review; all files were preserved.')
            data['phase'] = 'rolledBack'; save(journal, data)
            return {'layout': 1, 'changed': True}
        source = folder(target if target.exists() else stage)
        actual = inventory(source)
        if data['phase'] == 'rollingBack':
            for name in data['entries']:
                restored = project / name
                if restored.exists():
                    if (source / name).exists(): raise ProjectFault('Rollback name conflict; all data was preserved.')
                    if restored.is_dir():
                        actual.update({name + '/' + k: v for k, v in inventory(restored).items()})
                    else:
                        with restored.open('rb') as f: actual[name] = hashlib.file_digest(f, 'sha256').hexdigest()
        else:
            for name in data['entries']:
                if (project / name).exists(): raise ProjectFault('Rollback name conflict; all files were preserved.')
        if actual != data['hashes']:
            raise ProjectFault('Source files changed after migration; rollback preserved all versions.')
        data['phase'] = 'rollingBack'; save(journal, data)
        for name in data['entries']:
            if (source / name).exists():
                os.rename(source / name, project / name); sync(project); sync(source)
        source.rmdir(); sync(project)
        data['phase'] = 'rolledBack'; save(journal, data)
        return {'layout': 1, 'changed': True}
    if data['phase'] == 'rollingBack':
        raise ProjectFault('Resume the explicit rollback before proceeding.')
    if target.exists():
        folder(target)
        if inventory(target) != data['hashes'] and data['phase'] != 'complete':
            raise ProjectFault('Workspace changed during migration; all files were preserved.')
    else:
        stage.mkdir(mode=0o700, exist_ok=True); folder(stage)
        for name in data['entries']:
            old, new = project / name, stage / name
            if old.exists() and not new.exists():
                os.rename(old, new); sync(project); sync(stage)
            elif old.exists() or not new.exists():
                raise ProjectFault('Interrupted layout migration conflicts with edits; files were preserved.')
        if inventory(stage) != data['hashes']:
            raise ProjectFault('Project changed during migration; all files were preserved.')
        os.rename(stage, target); sync(project)
    data['phase'] = 'complete'; save(journal, data)
    return {'layout': 2, 'changed': True}
