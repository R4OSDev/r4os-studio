"""Capture the installed catalog for a run; session age is not a capability."""
import hashlib
import json
from tool_catalog import specifications, tool_scope


def snapshot(value,exclude=()):
    scope = tool_scope(value)
    declarations = [item for item in specifications(value) if item['name'] not in exclude]
    raw = json.dumps(declarations, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {'scope': scope, 'sha256': hashlib.sha256(raw).hexdigest(),
            'tools': [item['name'] for item in declarations]}


def verify(config):
    saved = config.get('toolCatalog')
    if saved is not None and saved != snapshot(config):
        raise ValueError('The original run catalog differs from its immutable worker release.')


def goal_selection(store,sid):
    session=store.get(sid)
    return {'permissions':session['permissions'].copy(),'catalog':snapshot(session)}


def instructions(config):
    return ('\n\nCURRENT STUDIO TOOLS: Use the declared tools and argument schemas for this run. '
            'Use the session permissions, workspace ownership, provider capabilities and guest/helper readiness '
            'to determine which operations are available. Use them within the user-authorized task and verify each effect from its result.')
