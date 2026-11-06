"""Small OAuth Messages compatibility mapping; Studio instructions stay intact.

Wire reference: ex-machina-co/opencode-anthropic-auth 93cdd23b95f8.
The connector adds identity/billing metadata, tool namespace and prompt caching.
No prompt sanitization, native runtime, conversation loop or tool execution.
"""
import hashlib

VERSION = '2.1.284'
PREFIX = 'mcp_'


def headers():
    return {'anthropic-beta': 'oauth-2025-04-20,interleaved-thinking-2025-05-14',
            'User-Agent': 'claude-cli/'+VERSION+' (external, cli)'}


def request(body, tools):
    from claude_tool_schema import input_schema
    names = {tool['name']: PREFIX+tool['name'] for tool in tools}
    for tool in body['tools']:
        tool['name'] = names[tool['name']]
        tool['input_schema'] = input_schema(tool['input_schema'])
    first = next((m for m in body['messages'] if m['role'] == 'user'), {})
    text = next((p['text'] for p in first.get('content', []) if p.get('type') == 'text'), '')
    # The original client's sampled indices are UTF-16 code units.
    units = text.encode('utf-16-le')
    sampled = b''.join(units[i*2:i*2+2] or b'0\0' for i in (4, 7, 20)).decode('utf-16-le', 'replace')
    suffix = hashlib.sha256(('59cf53e54c78'+sampled+VERSION).encode()).hexdigest()[:3]
    cch = hashlib.sha256(text.encode()).hexdigest()[:5]
    billing = f'x-anthropic-billing-header: cc_version={VERSION}.{suffix}; cc_entrypoint=sdk-cli; cch={cch};'
    original = body['system']
    body['system'] = [{'type': 'text', 'text': billing},
                      {'type': 'text', 'text': "You are a Claude agent, built on Anthropic's Claude Agent SDK."}]
    if original:
        body['system'].append({'type': 'text', 'text': original})
    # One stable tools/system prefix plus the growing conversation. Both use
    # the documented default five-minute TTL; no longer paid TTL is requested.
    # Signed assistant blocks and original tool schemas stay untouched.
    body['system'][-1]['cache_control'] = {'type': 'ephemeral'}
    body['cache_control'] = {'type': 'ephemeral'}
    return body
