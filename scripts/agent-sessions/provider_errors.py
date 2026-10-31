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
    'apiProtocolUnsupported': 'The selected API protocol cannot preserve this operation.',
    'apiInvalidToolArguments': 'The model sent invalid or incomplete tool arguments.',
    'apiProtocolError': 'The model response does not match the qualified Chat Completions protocol.',
    'apiStreamIncomplete': 'The model response stream ended before completing.',
    'apiOutputLimit': 'The model reached its output limit before completion.',
    'apiContentFilter': 'The model service blocked this response.',
    'apiAccountRequired': 'The API account needs credits or billing attention (HTTP402).',
    'apiAccessDenied': 'The API account cannot access this model (HTTP403).',
    'apiServiceUnavailable': 'The API model service is temporarily unavailable.',
    'apiModelOrRouteUnavailable': 'The selected model or API route was not found (HTTP404). Review the exact model ID and API prefix.',
    'responseBodyDecodeFailed': 'The model response connection failed while reading the response body.',
}
CONNECTIONS = {'httpConnectionFailed', 'responseStreamConnectionFailed',
               'responseStreamDisconnected', 'responseTooManyFailedAttempts'}
RESPONSE_BODY_DECODE_MESSAGE = (
    'stream disconnected before completion: Transport error: network error: error decoding response body')


def response_body_decode_failure(info, message):
    """Only the exact observed pinned-native failure, never a text substring."""
    return info == 'other' and message == RESPONSE_BODY_DECODE_MESSAGE


def describe(error,api=False):
    error = error if isinstance(error, dict) else {}
    info = error.get('codexErrorInfo'); status = None
    code = info if isinstance(info, str) and info in MESSAGES else 'unknown'
    if isinstance(info, dict) and len(info) == 1:
        candidate = next(iter(info))
        if candidate in CONNECTIONS and isinstance(info[candidate], dict):
            code = candidate; value = info[candidate].get('httpStatusCode')
            if type(value) is int and 100 <= value <= 599: status = value
    if response_body_decode_failure(info, error.get('message')):
        code = 'responseBodyDecodeFailed'
    connection_code=code
    if api and status==402:code='apiAccountRequired'
    if api and status==403:code='apiAccessDenied'
    if api and status==404:code='apiModelOrRouteUnavailable'
    if api and status==429:code='rateLimitExceeded'
    if api and status==503:code='apiServiceUnavailable'
    if api and (code=='unknown' and info=='other' or code=='responseStreamDisconnected'):
        # Codex0.163.0 retains HTTP400 Responses error JSON as Other rather
        # than its typed SSE classification. Decode only bounded, known codes
        # from the private relay's sanitized envelope; never render its text.
        raw=error.get('message')
        try:
            if isinstance(raw,str) and len(raw)<=4096:
                for prefix in ('stream disconnected before completion: ','stream error: '):
                    if raw.startswith(prefix):raw=raw[len(prefix):]
                terminal={'Incomplete response returned, reason: max_output_tokens':'apiOutputLimit',
                    'Incomplete response returned, reason: studio_chat_content_filter':'apiContentFilter'}
                code=terminal.get(raw,code)
            value=json.loads(raw) if isinstance(raw,str) and len(raw)<=4096 else None
            detail=value.get('error') if isinstance(value,dict) and set(value)=={'error'} else None
            candidate=detail.get('code') if isinstance(detail,dict) else None
            code={'context_length_exceeded':'contextWindowExceeded','usage_limit_exceeded':'usageLimitExceeded',
                'insufficient_quota':'usageLimitExceeded','rate_limit_exceeded':'rateLimitExceeded',
                'invalid_api_key':'unauthorized','model_not_found':'badRequest',
                'chat_semantics_unavailable':'apiProtocolUnsupported','chat_invalid_tool_arguments':'apiInvalidToolArguments',
                'api_server_semantics_unavailable':'apiProtocolUnsupported',
                'chat_protocol_error':'apiProtocolError','chat_stream_incomplete':'apiStreamIncomplete',
                'api_account_required':'apiAccountRequired','api_access_denied':'apiAccessDenied','api_service_unavailable':'apiServiceUnavailable'}.get(candidate,code) if isinstance(candidate,str) else code
        except (ValueError,TypeError):pass
    transient = code in ('httpConnectionFailed', 'responseStreamConnectionFailed') and status in (502, 503, 504)
    if code == 'responseBodyDecodeFailed': transient = True
    if api and status==503 and connection_code in ('httpConnectionFailed','responseStreamConnectionFailed','responseTooManyFailedAttempts'):transient=True
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
    if api and (code=='unauthorized' or status==401):message='The API key was rejected. Review this connection’s key and permissions (HTTP401).'
    return {'code': code, 'httpStatusCode': status, 'transientCandidate': transient, 'text': message}
