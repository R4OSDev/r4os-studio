"""Bound English guidance and allowlisted frozen data; saved texts stay exact."""
from tool_catalog import tool_scope
import json
from pathlib import Path
from profile import REMOTE_TOOLS


def compose(config):
    if config.get('owner', {}).get('type') != 'project': return ''
    permissions = config.get('permissions', {}); compatible = tool_scope(config) == 'project'
    permitted = {'studio.' + name: bool(compatible and permissions.get('studio.' + name) is True) for name in REMOTE_TOOLS}
    if not any(permitted.values()): return ''
    catalog = config.get('toolCatalog',{})
    if catalog.get('version')==2 and not any('studio_'+name in catalog['tools'] for name in REMOTE_TOOLS): return ''
    source = config.get('remoteHostContext') or config.get('remoteHostBinding')
    if not isinstance(source, dict):
        return '\n\nSTUDIO REMOTE HOST: No Remote Host is assigned for this run.'
    limits = {'id': 36, 'name': 120, 'description': 4000, 'address': 255, 'user': 64}
    host = {k: source[k][:limit] for k, limit in limits.items() if isinstance(source.get(k), str)}
    if type(source.get('port')) is int and 1 <= source['port'] <= 65535: host['port'] = source['port']
    key = source.get('hostKey') or {}; host['hostKey'] = {k: key[k] for k in ('state', 'fingerprint') if isinstance(key.get(k), str)}
    check = source.get('lastTest') or {}; host['lastCheck'] = {k: check[k] for k in ('status', 'version', 'kernel', 'checkedAt') if isinstance(check.get(k), str)}
    access = config.get('remoteHostAccess', {})
    value = {'defaultTarget': 'virtual_machine', 'assignedHost': host,
             'bindingFrozen': bool(config.get('remoteHostBinding')), 'projectToolsAvailable': compatible,
             'permissions': permitted,
             'workspaceFilePermissions': {name: permissions.get('studio.' + name) is True for name in ('read_file', 'write_file')},
             'availabilityReason': access.get('reason', 'This run has no frozen Remote Host metadata. Use the normal VM workflow; inspect availability for an explicit remote request.')}
    contract = Path(__file__).resolve().parents[2] / 'shared/remote-host-instructions.txt'
    return ('\n\n'
            + contract.read_text() + '\nBEGIN FROZEN REMOTE HOST DATA\n' + json.dumps(value, ensure_ascii=True, separators=(',', ':'))
            + '\nEND FROZEN REMOTE HOST DATA')
