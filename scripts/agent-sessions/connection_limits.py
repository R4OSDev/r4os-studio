"""Original account-limit reads over the existing private API credential owner."""
import hashlib
import json
import os
import time
import urllib.error

from api_provider_store import ApiProviders, private
from attachment_store import birth
from claude_plan import ClaudePlan, remote
from profile import directory, write_json
from session_store import identity, now
from store import ProjectFault

KINDS = ('claude-plan',)


def binding(provider):
    return {k: provider[k] for k in ('id', 'kind', 'baseUrl', 'protocol', 'revision', 'credentialRevision')}


def claude(body, provider, frozen, rid, received):
    from claude_limits_policy import reported_windows, window, WINDOWS
    data = body.get('rate_limits', body)
    if not isinstance(data, dict) or body.get('rate_limits_available') is False:
        raise ValueError()
    partial = False
    try:
        windows, extra, meters = reported_windows(data, strict=False)
    except (ValueError, TypeError, OverflowError):
        # An unknown quota field does not erase independently reported billing
        # settings or invent zero capacity in otherwise readable windows.
        windows = []; partial = True
        for key, label, scope in WINDOWS:
            if data.get(key) is None:continue
            try:windows.append(window(key, label, scope, data[key]))
            except (ValueError, TypeError, OverflowError):pass
        for field, prefix in (('limits', 'native-meter-'), ('model_scoped', 'model-scoped-')):
            rows = data.get(field)
            if not isinstance(rows, list) or len(rows) > 64:continue
            for index, row in enumerate(rows):
                try:parsed, _, _ = reported_windows({field: [row]}, strict=False)
                except (ValueError, TypeError, OverflowError):continue
                for value in parsed:
                    value['id'] = prefix+str(index)
                    windows.append(value)
        raw_extra = data.get('extra_usage')
        extra = raw_extra.get('is_enabled') if isinstance(raw_extra, dict) and type(raw_extra.get('is_enabled')) is bool else None
        meters = isinstance(data.get('limits'), list)
    complete = all(any(w['id'] == key and w['usedPercent'] is not None for w in windows) for key in ('five_hour', 'seven_day'))
    account = hashlib.sha256(json.dumps(frozen['identity'], sort_keys=True).encode()).hexdigest() if frozen['identity'] else None
    sample = {'schema': 1, 'source': 'studio-claude-oauth/usage', 'receivedAt': received,
              'providerId': provider['id'], 'providerRevision': provider['revision'], 'accountIdentity': account,
              'requestId': rid, 'plan': body.get('subscription_type') if body.get('subscription_type') in ('pro', 'max') else None,
              'coverage': 'available' if complete and not partial else 'partial' if windows else 'unavailable',
              'extraUsageEnabled': extra, 'serverMetersReported': meters, 'windows': windows,
              'message': 'Reported by the selected Claude subscription. Some quota fields are unavailable.' if partial else 'Reported by the selected Claude subscription. Missing windows remain unknown.'}
    percentages = [w['remainingPercent'] for w in windows if w['remainingPercent'] is not None]
    return {'remainingPercent': min(percentages) if percentages else None, 'claude': sample}, extra


class Limits:
    def __init__(self, providers):
        self.api = ApiProviders(providers)
        self.owner = ClaudePlan(providers)
        self.root = self.api.root/'Limits'

    def folder(self, child):
        private(self.api.root, directory=True)
        private(directory(self.root), directory=True)
        path = directory(self.root/child)
        private(path, directory=True)
        return path

    def path(self, ident):
        return self.folder('Snapshots')/(identity(ident)+'.json')

    def provider(self, ident):
        value = self.api.get(ident)
        if value['kind'] not in KINDS:
            raise ProjectFault('This connection has no account-limit reader.', 400)
        return value

    def record(self, provider):
        path = self.path(provider['id'])
        value = self.owner.read(path) if path.exists() else None
        return value if value and value['binding'] == binding(provider) else None

    def listing(self, ident, refresh=True):
        provider = self.provider(ident); value = self.record(provider)
        if refresh and provider['enabled'] and (not value or time.time()-value.get('lastAttemptAt', value['checkedAtUnix']) >= 60):
            import uuid
            self.refresh(ident, {'requestId': str(uuid.uuid4()), 'providerRevision': provider['revision']}, only_if_stale=True)
            value = self.record(provider)
        result = {'providerId': ident, 'configRevision': provider['revision'], 'credentialRevision': provider['credentialRevision'],
                  'checkedAt': None, 'remainingPercent': None, 'state': 'unknown', 'error': None}
        if value and provider['enabled']:
            result.update(value['public'], error=value.get('error'))
            result['state'] = 'current' if not value.get('error') and 0 <= time.time()-value['checkedAtUnix'] <= 60 else 'stale' if value['public'].get('checkedAt') else 'unknown'
        return result

    def receipt(self, ident, rid):
        self.api.get(ident)
        path = self.folder('Requests')/(identity(rid)+'.json')
        if not path.exists():
            raise ProjectFault('Original account-limit request not found.', 404)
        value = self.owner.read(path)
        if value['binding']['id'] != identity(ident):
            raise ProjectFault('This limit request belongs to another connection.', 404)
        result = dict(value['result'])
        if result['state'] == 'pending':
            try:
                ended = birth(value['controller']['pid']) != value['controller']['birth']
            except (OSError, ValueError):
                ended = True
            if ended:
                result.update(state='unknown', error='The original limit check ended without a confirmed response. It was not repeated.')
        return result

    def refresh(self, ident, data, only_if_stale=False):
        if not isinstance(data, dict) or set(data) != {'requestId', 'providerRevision'}:
            raise ProjectFault('Use an original request and current provider revision for the limit check.', 400)
        rid = identity(data['requestId']); ident = identity(ident)
        request_path = self.folder('Requests')/(rid+'.json')
        with self.owner.lock(request_path.with_suffix('.lock')):
            if request_path.exists():
                original = self.owner.read(request_path)
                if original['binding']['id'] != ident or original['input'] != data:
                    raise ProjectFault('This limit request already belongs to different input.', 409)
                return self.receipt(ident, rid)
            path = self.path(ident)
            with self.owner.lock(path.with_suffix('.lock')):
                provider = self.provider(ident)
                if not provider['enabled'] or type(data['providerRevision']) is not int or data['providerRevision'] != provider['revision']:
                    raise ProjectFault('The account connection changed. Reload before checking its limits.', 409)
                result = {'requestId': rid, 'providerId': ident, 'state': 'pending'}
                original = {'binding': binding(provider), 'input': data, 'createdAt': now(),
                            'controller': {'pid': os.getpid(), 'birth': birth(os.getpid())}, 'result': result}
                write_json(request_path, original)
                previous = self.record(provider)
                if only_if_stale and previous and 0 <= time.time()-previous.get('lastAttemptAt', previous['checkedAtUnix']) < 60:
                    original['result'] = {**result, 'state': 'failed' if previous.get('error') else 'complete'}
                    if previous.get('error'):original['result']['error']=previous['error']
                    original['cacheReused'] = True
                    write_json(request_path, original)
                    return original['result']
                try:
                    frozen = self.owner.frozen(provider)
                    access = self.owner.credential(provider, frozen)
                    body = remote('https://api.anthropic.com/api/oauth/usage', access=access)
                    if access in json.dumps(body):
                        raise ValueError()
                    if binding(self.api.get(ident)) != original['binding'] or not self.api.get(ident)['enabled']:
                        raise ProjectFault('This account changed during its original limit check.', 409)
                    received = now(); public, extra = claude(body, provider, frozen, rid, received)
                    public['checkedAt'] = received
                    value = {'binding': binding(provider), 'checkedAtUnix': time.time(), 'lastAttemptAt': time.time(), 'identity': frozen['identity'],
                             'extraUsageEnabled': extra, 'error': None, 'public': public}
                    write_json(path, value)
                    original['responseOriginal'] = body
                    result = {**result, 'state': 'complete'}
                except Exception as error:
                    message = 'Subscription limits are unavailable. No model request was made.'
                    if isinstance(error, urllib.error.HTTPError):
                        message = 'The account-limit reader returned HTTP '+str(error.code)+'. No alternate account was used.'
                    value = self.record(provider)
                    if not value:
                        value = {'binding': binding(provider), 'checkedAtUnix': 0, 'identity': None,
                                 'extraUsageEnabled': None, 'public': {'checkedAt': None, 'remainingPercent': None}}
                    value['error'] = message
                    value['lastAttemptAt'] = time.time()
                    write_json(path, value)
                    result = {**result, 'state': 'failed', 'error': message}
                original['result'] = result; original['finishedAt'] = now()
                write_json(request_path, original)
                return result

    def finish_reads(self, ident):
        path = self.path(ident)
        with self.owner.lock(path.with_suffix('.lock')):
            pass  # The original bounded reader has closed before credentials clear.
