"""Freeze only trusted assigned-VM metadata; no VM, SDK or provider operation."""
import json
from pathlib import Path
import re


def snapshot(store):
    project = store.project
    ident = project.get('vmId')
    value = {'version': 1, 'projectRevision': project['revision'], 'vmId': ident, 'available': False}
    if not ident:
        return {**value, 'reason': 'No VM was assigned when this input was accepted.'}
    try:
        if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise ValueError()
        root = Path(store.r4os).absolute()
        path = root / 'Instances' / ident / 'vm.json'
        if path.resolve(strict=True) != path or path.stat().st_size > 65536: raise ValueError()
        vm = json.loads(path.read_text())
        if vm['id'] != ident or not re.fullmatch('[a-f0-9]{64}', vm['imageSha256']): raise ValueError()
        return {**value, 'available': True, 'vmRevision': vm.get('revision', vm['imageSha256']),
                'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
    except (OSError, ValueError, KeyError, TypeError):
        return {**value, 'reason': 'The assigned VM identity was unavailable when this input was accepted.'}
