"""Actual working paths for new runs; saved prompts and histories stay intact."""
import json
from pathlib import Path


def snapshot(store, config):
    paths = {'workspace': str(store.workspace)}
    if store.owner_type == 'project':
        pins = config.get('projectPins', {})
        revision = pins.get('sdk', {}).get('revision')
        if revision:
            bundle = Path(store.r4os) / 'Packages' / revision / 'bundle.json'
            if bundle.is_file():
                values = json.loads(bundle.read_text())['paths']
                paths.update({name: str(Path(store.r4os) / value) for name, value in values.items()})
                if 'install' in paths: paths['zig'] = str(Path(paths['install']) / 'Toolchains/Zig')
    access = config.get('skillAccess') or {}
    if access.get('entries'):
        from skill_application import Snapshot
        revisions = Snapshot(store.projects)
        paths['skills'] = {entry['id']: str(revisions.revision(entry)[0]) for entry in access['entries']}
    return paths


def compose(config):
    path = (config.get('workspaceContext') or {}).get('workspace')
    text = ('\n\nSTUDIO WORKSPACE: Use the selected workspace unless the user specifies another location. '
            'Relative file paths and the default terminal workdir start there.')
    if path:
        text += ' Workspace path ' + json.dumps(path, ensure_ascii=True) + '.'
    if config.get('owner', {}).get('type') == 'project':
        text += ' Use the file-tool roots workspace, sdk and contract for the selected sources.'
    if config.get('permissions', {}).get('studio.exec_command'):
        text += (' Host commands run as Root. Use STUDIO_WORKSPACE and the paths in STUDIO_PATHS. '
                 'Project terminals expose the pinned SDK_ROOT and CONTRACT_ROOT when available.')
    return text
