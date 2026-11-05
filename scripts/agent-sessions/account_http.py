"""Bounded JSON transport for fixed account endpoints; no redirect or retry."""
import json
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, body=None, headers=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
        headers={'Accept': 'application/json', 'Accept-Encoding': 'identity', **(headers or {})})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
        raw = response.read(262145)
        if len(raw) > 262144 or response.headers.get('Content-Encoding'):
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
