"""Bounded presentation of native Codex web-search items; never fetches URLs."""
from urllib.parse import urlsplit


def text(value, limit):
    if not isinstance(value, str): return ''
    return ''.join(c for c in value if ord(c) >= 32 and not 127 <= ord(c) <= 159).encode()[:limit].decode('utf-8', errors='ignore')


def public_url(value):
    if not isinstance(value, str) or len(value.encode()) > 2048 or '\\' in value or any(ord(c) <= 32 or 127 <= ord(c) <= 159 for c in value): return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username is not None or parsed.password is not None: return None
        parsed.port
    except ValueError: return None
    return value


def presentation(native, run_id, completed=False):
    ident = native.get('id')
    if not isinstance(ident, str) or not ident or len(ident) > 160: raise ValueError('Invalid native search identity.')
    action = native.get('action') if isinstance(native.get('action'), dict) else {}
    kind = action.get('type', 'search')
    if kind not in ('search', 'openPage', 'findInPage'): kind = 'other'
    details = {'action': kind}
    query = text(native.get('query'), 2048)
    if kind == 'search':
        values = action.get('queries') if isinstance(action.get('queries'), list) else []
        values = values or [action.get('query') or query]
        queries = [text(v, 2048) for v in values[:8] if isinstance(v, str) and v.strip()]
        if queries: details['queries'] = queries
        if len(values) > 8 or any(isinstance(v, str) and len(v) > 2048 for v in values): details['truncated'] = True
    else:
        url = public_url(action.get('url'))
        if url: details['url'] = url
        pattern = text(action.get('pattern'), 512)
        if pattern: details['pattern'] = pattern
    sources, seen = [], set()
    results = native.get('results') if isinstance(native.get('results'), list) else []
    for result in results[:64]:
        if not isinstance(result, dict): continue
        url = public_url(result.get('url'))
        if not url or url in seen: continue
        seen.add(url); sources.append({'title': text(result.get('title'), 256) or url, 'url': url})
        if len(sources) == 24: break
    if sources: details['sources'] = sources
    if len(results) > 64 or len(sources) == 24: details['truncated'] = True
    arguments = {k: v for k, v in details.items() if k not in ('sources', 'truncated')}
    return {'id': ident, 'runId': run_id, 'type': 'tool', 'tool': 'web_search',
            'status': 'completed' if completed else 'pending', 'arguments': arguments,
            'webSearch': details, 'truncated': details.get('truncated', False)}
