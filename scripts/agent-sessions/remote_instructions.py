"""Bound English guidance and allowlisted frozen data; saved texts stay exact."""
import json
from pathlib import Path
from profile import REMOTE_TOOLS
from tool_catalog import tool_scope


def compose(config):
    if config.get('owner', {}).get('type') != 'project' or tool_scope(config) != 'project':
        return ''
    permissions = config.get('permissions', {})
    names = {'studio_' + name for name in REMOTE_TOOLS if permissions.get('studio.' + name) is True}
    catalog = config.get('toolCatalog', {})
    if catalog.get('version') == 2:
        actions = catalog.get('actions', {}).get('studio_remote_job', ())
        job_available = any('studio_' + action + '_remote_job' in names for action in actions)
        names &= set(catalog['tools'])
        if job_available:
            names.add('studio_remote_job')
    if not names:
        return ''
    source = config.get('remoteHostContext') or config.get('remoteHostBinding')
    if not isinstance(source, dict):
        if 'studio_remote_job' in names:
            return ('\n\nSTUDIO REMOTE HOST: Use the declared actions on this session’s original jobs. '
                    'Preserve the original requestId and distinguish client exit from confirmed remote effects.')
        return '\n\nSTUDIO REMOTE HOST: No Remote Host is assigned for this run.'
    host = {key: source[key][:limit] for key, limit in (('id', 36), ('name', 120))
            if isinstance(source.get(key), str)}
    contract = Path(__file__).resolve().parents[2] / 'shared/remote-host-instructions.txt'
    return ('\n\n' + contract.read_text() + '\nBEGIN FROZEN REMOTE HOST DATA\n'
            + json.dumps({'assignedHost': host}, ensure_ascii=True, separators=(',', ':'))
            + '\nEND FROZEN REMOTE HOST DATA')
