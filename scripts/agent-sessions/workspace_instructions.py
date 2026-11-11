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
    paths = config.get('workspaceContext')
    return ('\n\nSTUDIO WORKSPACE: Studio runs directly as host Root in a trusted environment. '
        'Use the selected workspace as the working directory and keep task changes there unless the task calls for another location. '
        'Relative file paths and omitted terminal workdir use that workspace. Absolute host paths, parent paths and symlinks use normal host semantics. '
        'The workspace is an orientation, with no filesystem, process or network sandbox. '
        'File tools resolve named roots and structured /workspace or SDK paths to the actual paths of this run. '
        'In terminals use STUDIO_WORKSPACE, SDK_ROOT, CONTRACT_ROOT and SDK_TOOLS_ROOT or actual paths. '
        'User authorization, selected tool availability and original job/receipt identities still apply. '
        + ('Actual working paths: ' + json.dumps(paths, ensure_ascii=False, sort_keys=True) + '.' if paths else ''))
