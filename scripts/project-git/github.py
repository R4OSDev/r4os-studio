"""Fixed GitHub HTTPS contract and private credential broker; no redirects."""
import json
from pathlib import Path
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from common import ProjectFault, document, name


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args): return None


class GitHub:
    def __init__(self, directory, connection_id, token_revision=None, expected_user=None):
        self.directory, self.connection_id = Path(directory), connection_id
        record = self.snapshot()
        self.token_revision = record.get('tokenRevision', 1)
        if token_revision is not None and token_revision != self.token_revision:
            raise ProjectFault('GitHub token changed. Refresh the connection.', 409)
        self.token = record['token']; self.connection_name = record['name']
        account = self.request('/user')
        if not isinstance(account, dict) or not isinstance(account.get('id'), int) or account['id'] <= 0:
            raise ProjectFault('GitHub account could not be verified.', 502)
        name(account.get('login'), True)
        if expected_user is not None and account['id'] != expected_user:
            raise ProjectFault('This connection now authenticates another account. Reconnect explicitly.', 409)
        self.user = {'login': account['login'], 'id': account['id']}
        self.assert_current()

    def snapshot(self):
        catalog = document(self.directory / 'connections.json', 8 * 1024 * 1024)
        if catalog.get('schema') != 1 or not isinstance(catalog.get('connections'), list):
            raise ProjectFault('GitHub connection storage needs maintenance.', 503)
        record = next((v for v in catalog['connections'] if v.get('id') == self.connection_id), None)
        if not record: raise ProjectFault('GitHub connection was removed. Reconnect this project.', 409)
        if not isinstance(record.get('token'), str) or not re.fullmatch(r'[\x21-\x7e]{20,4096}', record['token']):
            raise ProjectFault('GitHub connection storage is invalid.', 503)
        return record

    def assert_current(self):
        record = self.snapshot()
        if record.get('tokenRevision', 1) != self.token_revision or record['token'] != self.token:
            raise ProjectFault('GitHub token changed during the operation. Reconcile its original result.', 409)

    def request(self, path, method='GET', body=None):
        if not path.startswith('/') or path.startswith('//') or any(c in path for c in '\r\n#'):
            raise ProjectFault('Invalid GitHub operation.', 400)
        self.assert_current() if hasattr(self, 'token_revision') else None
        payload = None if body is None else json.dumps(body).encode()
        request = Request('https://api.github.com' + path, data=payload, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'R4OS-Studio', 'Content-Type': 'application/json'})
        try:
            with build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context())).open(request, timeout=10) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024: raise ProjectFault('GitHub response exceeded its limit.', 502)
                return json.loads(raw)
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 404: raise ProjectFault('GitHub repository or branch is unavailable to this token.', 404) from None
            if status in (401, 403, 429): raise ProjectFault('GitHub denied this operation. Check connection, permissions, SSO and rate limits.', status) from None
            if status == 422: raise ProjectFault('GitHub rejected the name or repository parameters.', 422) from None
            raise ProjectFault('GitHub operation did not return a confirmed result.', 502) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProjectFault('GitHub network response could not be confirmed. Reconcile this operation.', 503) from None

    def repository(self, owner, repo, expected_id=None):
        name(owner, True); name(repo)
        value = self.request('/repos/' + owner + '/' + repo)
        if (not isinstance(value.get('id'), int) or value['id'] <= 0 or value.get('full_name') != value.get('owner', {}).get('login', '') + '/' + value.get('name', '')
                or (expected_id is not None and value['id'] != expected_id)):
            raise ProjectFault('GitHub repository identity changed. Reconnect explicitly.', 409)
        name(value['owner']['login'], True); name(value['name'])
        return {'id': value['id'], 'owner': value['owner']['login'], 'name': value['name'], 'fullName': value['full_name'],
                'url': 'https://github.com/' + value['full_name'], 'private': value.get('private') is True,
                'defaultBranch': value.get('default_branch'), 'archived': value.get('archived') is True,
                'read': value.get('permissions', {}).get('pull') is True or value.get('private') is False,
                'push': value.get('permissions', {}).get('push') is True and value.get('archived') is not True}
