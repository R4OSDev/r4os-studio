"""Safe native error descriptions. A transient candidate never authorizes replay."""
import re
import json

MESSAGES = {
    'usageLimitExceeded': 'This provider has reached its usage limit.',
    'rateLimitExceeded': 'The model service is rate limited. Try again later.',
    'unauthorized': 'The provider needs to sign in again.',
    'contextWindowExceeded': 'The conversation exceeds the model context limit.',
    'sessionBudgetExceeded': 'The session reached its model budget.',
    'flexUnavailable': 'The selected model service tier is temporarily unavailable.',
    'serverOverloaded': 'The model service is overloaded.',
    'internalServerError': 'The model service reported an internal error.',
    'badRequest': 'The model service rejected the request.',
    'cyberPolicy': 'The model service blocked this request.',
    'misalignmentPolicyViolation': 'The model service blocked this request.',
    'tooManyDenials': 'The model run stopped after repeated denials.',
    'sandboxError': 'The native agent environment reported an error.',
}
CONNECTIONS = {'httpConnectionFailed', 'responseStreamConnectionFailed',
               'responseStreamDisconnected', 'responseTooManyFailedAttempts'}


def describe(error,api=False):
    error = error if isinstance(error, dict) else {}
    info = error.get('codexErrorInfo'); status = None
    code = info if isinstance(info, str) and info in MESSAGES else 'unknown'
    if isinstance(info, dict) and len(info) == 1:
        candidate = next(iter(info))
        if candidate in CONNECTIONS and isinstance(info[candidate], dict):
            code = candidate; value = info[candidate].get('httpStatusCode')
            if type(value) is int and 100 <= value <= 599: status = value
    if api and code=='unknown' and info=='other':
        # Codex0.163.0 retains HTTP400 Responses error JSON as Other rather
        # than its typed SSE classification. Decode only bounded, known codes
        # from the private relay's sanitized envelope; never render its text.
        raw=error.get('message')
        try:
            value=json.loads(raw) if isinstance(raw,str) and len(raw)<=4096 else None
            detail=value.get('error') if isinstance(value,dict) and set(value)=={'error'} else None
            candidate=detail.get('code') if isinstance(detail,dict) else None
            code={'context_length_exceeded':'contextWindowExceeded','usage_limit_exceeded':'usageLimitExceeded',
                'insufficient_quota':'usageLimitExceeded','rate_limit_exceeded':'rateLimitExceeded',
                'invalid_api_key':'unauthorized','model_not_found':'badRequest'}.get(candidate,'unknown') if isinstance(candidate,str) else 'unknown'
        except (ValueError,TypeError):pass
    transient = code in ('httpConnectionFailed', 'responseStreamConnectionFailed') and status in (502, 503, 504)
    message = MESSAGES.get(code, 'The model service reported an error.')
    if code in CONNECTIONS:
        suffix = f' (HTTP{status}).' if status is not None else '.'
        if code == 'responseStreamDisconnected': message = 'The model response stream ended before completion' + suffix
        elif code == 'responseTooManyFailedAttempts': message = 'The native provider retry limit was reached' + suffix
        elif status == 401: message = 'The provider needs to sign in again (HTTP401).'
        elif status == 403: message = 'Model access was denied (HTTP403).'
        elif status == 429: message = 'The model service is rate limited (HTTP429).'
        elif status == 503: message = 'Model service unavailable (HTTP503).'
        elif status == 502: message = 'Model gateway unavailable (HTTP502).'
        elif status == 504: message = 'Model gateway timed out (HTTP504).'
        else: message = 'The model service connection failed' + suffix
    elif code == 'unknown':
        # Retain only the previous narrow authentication/quota fallback. No
        # provider message, URL, request identifier or arbitrary code is exposed.
        raw = error.get('message'); raw = raw[:4096] if isinstance(raw, str) else ''
        if re.search(r'\b401\b|\bunauthorized\b', raw, re.I): message = MESSAGES['unauthorized']
        elif re.search(r'\b429\b|usage limit|quota exceeded', raw, re.I): message = MESSAGES['usageLimitExceeded']
    return {'code': code, 'httpStatusCode': status, 'transientCandidate': transient, 'text': message}
