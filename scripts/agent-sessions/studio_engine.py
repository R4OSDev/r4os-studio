"""The installed Studio worker identity; no model runtime discovery or probe."""
import hashlib
import json
from pathlib import Path
import re


def model_binding(provider):
    """Public model inputs only; account clients never own Studio execution."""
    from store import ProjectFault
    if provider.get('protocol') not in ('responses', 'chat-completions', 'messages'):
        raise ProjectFault('This connection has no supported model transport.', 409)
    value = {key: provider[key] for key in
             ('id', 'kind', 'baseUrl', 'protocol', 'auth', 'revision', 'credentialRevision')}
    if provider['kind'] == 'openrouter':
        import copy
        value['openrouter'] = copy.deepcopy(provider['openrouter'])
    else:
        value['server'] = provider.get('server', 'custom')
    if provider.get('inputTokenCounting') is True:value['inputTokenCounting']=True
    return value


def model_route(provider):
    return {**{key: provider[key] for key in ('kind', 'baseUrl', 'protocol')},
            'server': provider.get('server', 'custom'), 'providerId': provider['id']}


def release_for(value,current,root=Path('/opt/r4os-studio/releases')):
    """Use the immutable worker accepted with this input, including old queues."""
    from store import ProjectFault
    if value.get('kind')!='studio':return current
    version=value.get('version');checksum=value.get('sha256')
    if (not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version)
            or not isinstance(checksum,str) or not re.fullmatch(r'[a-f0-9]{64}',checksum)):
        raise ProjectFault('The accepted Studio worker identity is invalid. The input was preserved.',409)
    for candidate in [current,*sorted(root.glob(version+'-*'))]:
        try:
            candidate=candidate.resolve(strict=True)
            if not candidate.is_relative_to(root):continue
            info=json.loads((candidate/'release.json').read_text())
            if info['version']==version and hashlib.sha256((candidate/'scripts/agent-sessions/studio_worker.py').read_bytes()).hexdigest()==checksum:return candidate
        except (OSError,KeyError,ValueError):continue
    raise ProjectFault('The original immutable Studio worker is unavailable. The accepted input was preserved; select no replacement automatically.',409)


def engine(scope, api=None):
    root = Path(__file__).resolve().parents[2]
    value = {'kind': 'studio', 'toolScope': scope, 'available': True,
             'version': json.loads((root / 'shared/version.json').read_text())['version'],
             'sha256': hashlib.sha256(Path(__file__).with_name('studio_worker.py').read_bytes()).hexdigest()}
    if api: value['api'] = dict(api)
    return value
