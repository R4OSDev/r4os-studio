"""Browser PKCE and one private credential owner for Studio's Claude connector.

OAuth wire reference: ex-machina-co/opencode-anthropic-auth 93cdd23b95f8.
No native credential import, CLI, agent loop or model request lives here.
"""
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
from urllib.parse import parse_qs, urlencode, urlsplit

from api_provider_store import ApiProviders, private, name, key
from profile import directory, write_json
from session_store import identity, now
from store import ProjectFault

KIND = 'claude-plan'
BASE = 'https://api.anthropic.com/v1'
CLIENT = '9d1c250a-e61b-44d9-88ed-5944d1962f5e'
CALLBACK = 'https://platform.claude.com/oauth/code/callback'
TOKEN = 'https://platform.claude.com/v1/oauth/token'
SCOPES = 'org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload'
PREFIX = 'studio-claude-grant:'


def require(value):
    if any(value.get(k) != v for k, v in {'kind': KIND, 'baseUrl': BASE, 'protocol': 'messages', 'auth': 'bearer', 'server': 'custom'}.items()):
        raise ProjectFault('Claude subscription access requires its original browser grant and Messages endpoint.', 409)


def remote(url, body=None, access=None):
    from account_http import request_json
    headers = {'User-Agent': 'axios/1.13.6'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if access:
        from claude_wire import headers as oauth_headers
        headers['User-Agent'] = oauth_headers()['User-Agent']
        headers.update(Authorization='Bearer '+access, **{'anthropic-beta': 'oauth-2025-04-20'})
    return request_json(url, body, headers)


class ClaudePlan:
    def __init__(self, providers):
        self.api = ApiProviders(providers)
        self.root = self.api.root/'ClaudePlan'

    def folder(self, child):
        private(self.api.parent, directory=True)
        if not (self.api.root/'Providers.sqlite').exists():
            with self.api.connect(write=True):
                pass
        private(self.api.root, directory=True, create=True)
        private(directory(self.root), directory=True)
        path = directory(self.root/child)
        private(path, directory=True)
        return path

    def read(self, path):
        private(path)
        if path.stat().st_size > 262144:
            raise ProjectFault('The private Claude grant exceeds its bound.', 409)
        return json.loads(path.read_text())

    @contextmanager
    def lock(self, path):
        fd = os.open(path, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a') as file:
            private(path)
            fcntl.flock(file, fcntl.LOCK_EX)
            yield

    def attempt(self, rid):
        return self.folder('Attempts')/(identity(rid)+'.json')

    def owner(self, owner):
        from claude_auth_store import browser_owner
        return browser_owner(owner)

    def view(self, value):
        state = value['state']
        if state == 'waiting' and value['expiresAt'] <= time.time():
            state = 'expired'
        if state == 'exchanging':
            from attachment_store import birth
            try:
                if birth(value['controller']['pid']) != value['controller']['birth']:
                    state = 'unknown'
            except (OSError, ValueError, KeyError):
                state = 'unknown'
        result = {k: value.get(k) for k in ('requestId', 'name', 'providerId', 'message', 'createdAt')}
        result['state'] = state
        if state == 'waiting':
            result['authorizationUrl'] = value['authorizationUrl']
        return result

    def listing(self, owner):
        owner = self.owner(owner)
        values = [self.read(p) for p in self.folder('Attempts').glob('*.json')]
        return {'attempts': [self.view(v) for v in values if v['owner'] == owner],
                'accounts': [{'providerId': p['id']} for p in self.api.listing() if p['kind'] == KIND]}

    def start(self, data, owner):
        if not isinstance(data, dict) or set(data) != {'requestId', 'name'}:
            raise ProjectFault('Enter a display name and original sign-in request.', 400)
        rid = identity(data['requestId']); label = name(data['name']); owner = self.owner(owner)
        path = self.attempt(rid)
        with self.lock(path.with_suffix('.lock')):
            if path.exists():
                original = self.read(path)
                if original['owner'] != owner or original['name'] != label:
                    raise ProjectFault('This original sign-in belongs to different input or browser ownership.', 409)
                return self.view(original)
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            state = secrets.token_hex(16)
            value = {'requestId': rid, 'name': label, 'owner': owner, 'providerId': None,
                     'state': 'waiting', 'message': None, 'createdAt': now(), 'expiresAt': time.time()+600,
                     'verifier': verifier, 'oauthState': state,
                     'authorizationUrl': 'https://claude.ai/oauth/authorize?'+urlencode({
                         'code': 'true', 'client_id': CLIENT, 'response_type': 'code', 'redirect_uri': CALLBACK,
                         'scope': SCOPES, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': state})}
            write_json(path, value)
        return self.view(value)

    def owned(self, path, owner):
        value = self.read(path)
        if value['owner'] != self.owner(owner):
            raise ProjectFault('This sign-in is not available in this browser session.', 404)
        return value

    def cancel(self, rid, owner):
        path = self.attempt(rid)
        with self.lock(path.with_suffix('.lock')):
            value = self.owned(path, owner)
            if value['state'] == 'waiting':
                value.update(state='cancelled', message='Sign-in cancelled. No authorization code was exchanged.')
                value.pop('verifier', None)
                write_json(path, value)
        return self.view(value)

    def callback(self, rid, url, owner):
        path = self.attempt(rid)
        with self.lock(path.with_suffix('.lock')):
            value = self.owned(path, owner)
            if not isinstance(url, str) or not 1 <= len(url) <= 16384 or any(ord(c) < 33 for c in url):
                raise ProjectFault('Paste the complete redirect address from this sign-in.', 400)
            digest = hashlib.sha256(url.encode()).hexdigest()
            if value.get('submission'):
                if not hmac.compare_digest(value['submission'], digest):
                    raise ProjectFault('This sign-in already received a different redirect. Read its original result.', 409)
                return self.view(value)
            if value['state'] != 'waiting' or value['expiresAt'] <= time.time():
                raise ProjectFault('This original sign-in is no longer waiting. Start a new sign-in explicitly.', 409)
            try:
                returned = urlsplit(url); expected = urlsplit(CALLBACK)
                query = parse_qs(returned.query, keep_blank_values=True, strict_parsing=True)
                if ((returned.scheme, returned.netloc, returned.path) != (expected.scheme, expected.netloc, expected.path)
                        or returned.fragment or any(len(v) != 1 for v in query.values())
                        or set(query)-{'code', 'state', 'error', 'error_description'}):
                    raise ValueError()
                state = query.get('state', [''])[0]; code = query.get('code', [''])[0]
                if not state and code.count('#') == 1:
                    code, state = code.split('#')
                if not hmac.compare_digest(state, value['oauthState']) or not code or len(code) > 8192 or query.get('error'):
                    raise ValueError()
            except ValueError:
                raise ProjectFault('This redirect does not match the original Claude sign-in.', 400) from None
            # Persist before the one exchange. A crash/lost reply never replays it.
            from attachment_store import birth
            value.update(state='exchanging', submission=digest, controller={'pid': os.getpid(), 'birth': birth(os.getpid())})
            write_json(path, value)
            try:
                grant = self.tokens(remote(TOKEN, {'code': code, 'state': state, 'grant_type': 'authorization_code',
                    'client_id': CLIENT, 'redirect_uri': CALLBACK, 'code_verifier': value['verifier']}))
                grant_path = self.folder('Grants')/(rid+'.json')
                write_json(grant_path, grant)
                result = self.api.mutate('create', None, {'requestId': rid, 'name': value['name'], 'kind': KIND,
                    'baseUrl': BASE, 'protocol': 'messages', 'auth': 'bearer', 'key': PREFIX+rid}, plan=True)
                grant.update(providerId=result['provider']['id'], credentialRevision=result['provider']['credentialRevision'])
                write_json(grant_path, grant)
                value.update(state='complete', providerId=grant['providerId'], message='Connected. Model access is qualified separately.')
            except urllib.error.HTTPError as error:
                value.update(state='failed', message='Claude rejected the original sign-in exchange (HTTP '+str(error.code)+'). Start a new sign-in explicitly.')
            except Exception:
                value.update(state='unknown', message='The original sign-in exchange could not be confirmed. It was not repeated.')
            value.pop('verifier', None)
            write_json(path, value)
        return self.view(value)

    def tokens(self, body):
        access = key(body.get('access_token')); refresh = key(body.get('refresh_token'))
        lifetime = body.get('expires_in')
        if type(lifetime) not in (int, float) or not 1 <= lifetime <= 31*86400:
            raise ValueError()
        account = body.get('account'); organization = body.get('organization')
        # Only actually supplied identity, never an identity inferred from email.
        identity_fields = {k: v for k, v in {'account': account.get('uuid') if isinstance(account, dict) else None,
                           'organization': organization.get('uuid') if isinstance(organization, dict) else None}.items()
                           if isinstance(v, str) and len(v) <= 320}
        return {'access': access, 'refresh': refresh, 'expiresAt': time.time()+lifetime,
                'identity': identity_fields, 'scope': body.get('scope') if isinstance(body.get('scope'), str) else None}

    def frozen(self, provider):
        require(provider)
        with self.api.connect() as db:
            row = db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',
                             (provider['id'], provider['credentialRevision'])).fetchone()
            if not row or not row[0].startswith(PREFIX):
                raise ProjectFault('The original Claude browser grant is unavailable.', 409)
            rid = identity(row[0][len(PREFIX):])
        grant = self.read(self.folder('Grants')/(rid+'.json'))
        if grant.get('providerId') != provider['id'] or grant.get('credentialRevision') != provider['credentialRevision'] or grant.get('revoked'):
            raise ProjectFault('The original Claude account generation changed.', 409)
        return {'grantId': rid, 'identity': grant['identity']}

    def credential(self, provider, frozen):
        current = self.api.get(provider['id'])
        if not current['enabled'] or current['credentialRevision'] != provider['credentialRevision'] or self.frozen(provider) != frozen:
            raise ProjectFault('The original Claude access was disconnected or changed.', 409)
        path = self.folder('Grants')/(identity(frozen['grantId'])+'.json')
        with self.lock(path.with_suffix('.lock')):
            value = self.read(path)
            if value.get('refreshState') == 'exchanging':
                raise ProjectFault('The original Claude token renewal is unconfirmed. Sign in again explicitly.', 409)
            if value['expiresAt'] <= time.time()+60:
                value['refreshState'] = 'exchanging'; write_json(path, value)
                try:
                    fresh = self.tokens(remote(TOKEN, {'grant_type': 'refresh_token', 'refresh_token': value['refresh'], 'client_id': CLIENT}))
                    if fresh['identity'] and fresh['identity'] != value['identity']:
                        raise ValueError()
                    value.update(access=fresh['access'], refresh=fresh['refresh'], expiresAt=fresh['expiresAt'], refreshState='complete')
                    write_json(path, value)
                except Exception:
                    raise ProjectFault('Claude token renewal could not be confirmed. Sign in again explicitly; no token was retried.', 409) from None
            return value['access']

    def forget(self, ident):
        provider = self.api.get(ident)
        with self.api.connect() as db:
            if provider['enabled'] or db.execute("SELECT 1 FROM leases WHERE provider_id=? AND state!='released'", (ident,)).fetchone():
                raise ProjectFault('Confirm the original Claude worker ends before clearing sign-in.', 409)
        for path in self.folder('Grants').glob('*.json'):
            with self.lock(path.with_suffix('.lock')):
                value = self.read(path)
                if value.get('providerId') == ident:
                    write_json(path, {'providerId': ident, 'revoked': True, 'localLogoutAt': now(), 'remoteRevocation': 'unconfirmed'})

    def require_included(self, provider):
        from connection_limits import Limits
        import uuid
        current = self.api.get(provider['id'])
        if not current['enabled'] or current['credentialRevision'] != provider['credentialRevision']:
            raise ProjectFault('The original Claude subscription access changed.', 409)
        reader = Limits(self.api.parent)
        value = reader.record(current) or {}
        if value.get('error') or not 0 <= time.time()-value.get('checkedAtUnix', 0) <= 60:
            reader.refresh(provider['id'], {'requestId': str(uuid.uuid4()), 'providerRevision': current['revision']}, only_if_stale=True)
            value = reader.record(current) or {}
        if (value.get('binding', {}).get('id') != provider['id'] or value.get('binding', {}).get('credentialRevision') != provider['credentialRevision']
                or value.get('identity') != self.frozen(provider)['identity']
                or not 0 <= time.time()-value.get('checkedAtUnix', 0) < 90
                or value.get('extraUsageEnabled') is not False or value.get('error')):
            raise ProjectFault('Refresh Claude subscription limits to confirm included usage and disabled paid extra usage before running.', 409)
