"""Capture the installed catalog for a run; session age is not a capability."""
import hashlib
import json
from tool_catalog import specifications, tool_scope


def snapshot(value):
    scope = tool_scope(value)
    declarations = specifications(scope)
    raw = json.dumps(declarations, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {'scope': scope, 'sha256': hashlib.sha256(raw).hexdigest(),
            'tools': [item['name'] for item in declarations]}


def verify(config):
    saved = config.get('toolCatalog')
    if saved is not None and saved != snapshot(config):
        raise ValueError('The original run catalog differs from its immutable worker release.')


def instructions(config):
    return ('\n\nCURRENT STUDIO TOOLS: Use the tools and argument schemas currently declared for this run. '
            'Existing conversations receive the installed tool catalog on continuation. Earlier messages '
            'about an old Studio tool profile or needing a new session for newer tools are obsolete. '
            'Do not request a replacement conversation solely for tool availability. Saved disabled '
            'permissions, workspace ownership, actual provider capabilities and guest/helper readiness '
            'still apply. An available tool does not authorize an effect or prove an old effect completed.')
