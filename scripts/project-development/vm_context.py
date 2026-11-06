"""Small read-only assignment snapshot for the agent's input admission boundary."""
from pathlib import Path
import re

from contracts import DevelopmentFault, identity
from store import connect, ProjectFault


def snapshot(config, project_id):
    db = connect(Path(config['projects']), read_only=True)
    try:
        project = db.execute("SELECT vm_id, revision FROM projects WHERE id=? AND state='ready'", (identity(project_id),)).fetchone()
    finally: db.close()
    if project is None: raise ProjectFault('Project not found.', 404)
    ident = project['vm_id']
    value = {'version': 1, 'projectRevision': project['revision'], 'vmId': ident, 'available': False}
    if not ident: return value
    try:
        path = Path(config['r4os']) / 'Instances' / identity(ident) / 'vm.json'
        if path.resolve(strict=True) != path or path.stat().st_size > 65536: raise ValueError()
        from access import vm_config
        vm = vm_config(config['r4os'], ident)
        if (not re.fullmatch('[a-f0-9]{64}', vm['imageSha256'])
                or any(not isinstance(vm[key], str) or not 1 <= len(vm[key]) <= 128 for key in ('revision', 'imageId'))):
            raise ValueError()
        return {**value, 'available': True, 'vmRevision': vm['revision'],
                'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
    except (DevelopmentFault, OSError, ValueError, KeyError, TypeError): return value
