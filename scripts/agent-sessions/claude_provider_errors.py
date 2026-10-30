"""Bounded native Claude diagnostics; never a request replay authorization.

The pinned terminal result exposes an HTTP status, but not an independently
qualified pre-response continuation permit. Preserve that distinction and keep
auth, quota, policy and original-context refusals ahead of server diagnostics.
"""

SOURCE = 'claude-code-2.1.312/sdk-0.3.312/result'
RETRY_SOURCE = 'claude-code-2.1.312/sdk-0.3.312/api_retry'
ASSISTANT_ERRORS = {
    'authentication_failed': ('authentication', 'Claude sign-in is no longer valid. Check this provider before continuing.'),
    'oauth_org_not_allowed': ('authentication', 'This Claude organization does not allow the selected subscription session.'),
    'account_on_hold': ('authentication', 'Claude reports that this account is on hold.'),
    'verification_required': ('authentication', 'Claude requires account verification before continuing.'),
    'billing_error': ('quota', 'Claude rejected the subscription state. No API billing fallback was used.'),
    'rate_limit': ('quota', 'Claude limited this request. Check subscription limits before continuing.'),
    'invalid_request': ('request', 'Claude rejected this request. Check the selected model and session settings.'),
    'model_not_found': ('model', 'The selected Claude model is unavailable for this account. No replacement was used.'),
    'max_output_tokens': ('output', 'Claude reached the response output limit. Inspect its retained result.'),
    'cloud_credential_error': ('authentication', 'Claude reported an unexpected cloud credential state.'),
}
KIND_GROUPS = {
    'authentication': {'tls_untrusted_ca', 'gateway_signin_required', 'gateway_session_expired',
                       'provider_credentials', 'api_key_auth_disabled', 'org_disabled_credential', 'invalid_credential_header'},
    'quota': {'model_requires_usage_credits', 'long_context_credits_required', 'usage_limit_reached', 'unattended_start_limit'},
    'policy': {'dlp_request_denied', 'safety_monitor_blocked', 'consent_unanswered', 'field_not_granted'},
    'context': {'tool_history_mismatch', 'autocompact_thrashing', 'pdf_too_large', 'pdf_password_protected', 'media_removed'},
    'request': {'claude_code_version_too_old', 'effort_requires_thinking', 'advisor_incompatible',
                'no_allowed_fallback', 'model_substitution_disabled', 'gateway_content_type'},
    'output': {'max_output_tokens', 'empty_completion'},
    'unavailable': {'no_response', 'unattended_start_unconfirmed'},
}
GROUP_MESSAGES = {
    'authentication': 'Claude could not confirm its original authentication or TLS state. Check this provider.',
    'quota': 'Claude declined this request because of its subscription or usage limits. No billing fallback was used.',
    'policy': 'Claude blocked this request under its policy or consent rules.',
    'context': 'Claude could not preserve the original context or input. Review the retained session result.',
    'request': 'Claude rejected the original model or request contract. No replacement was used.',
    'output': 'Claude could not complete the response within its output contract. Review the retained result.',
    'unavailable': 'The original Claude request has no qualified completion. Review its retained result.',
}


def status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


def wire_observation(value):
    """Finite, passive facts; even noResponseObserved grants no continuation."""
    flags = ('inputReceiptObserved', 'toolUseObserved', 'nativeRetryObserved', 'compactionObserved', 'abandonedResponseObserved')
    counts = ('streamStarts', 'streamStops', 'assistantSnapshots')
    states = ('unknown', 'noResponseObserved', 'partialResponseObserved',
              'completeResponsesObserved', 'snapshotWithoutStreamBoundary')
    if (not isinstance(value, dict) or type(value.get('schema')) is not int or value.get('schema') != 1
            or value.get('state') not in states or value.get('retryAllowed') is not False
            or any(type(value.get(key)) is not bool for key in flags)
            or any(value.get(key) is not None and (type(value[key]) is not int or not 0 <= value[key] <= 65535)
                   for key in counts)):
        return None
    return {'schema': 1, 'state': value['state'], **{key: value[key] for key in flags},
            **{key: value.get(key) for key in counts}, 'retryAllowed': False}


def describe(value, assistant_code=None, native_retry=False):
    value = value if (isinstance(value, dict) and type(value.get('schema')) is int
                      and value.get('schema') == 1 and value.get('source') == SOURCE) else {}
    number = status(value.get('httpStatusCode'))
    candidate = value.get('kind')
    kind = candidate if isinstance(candidate, str) else None
    code, category, text = 'nativeError', 'unknown', 'Claude could not complete this original request.'
    assistant = ASSISTANT_ERRORS.get(assistant_code) if isinstance(assistant_code, str) else None
    group = next((group for group, kinds in KIND_GROUPS.items() if kind in kinds), None)
    if assistant and (assistant[0] in ('authentication', 'quota') or group is None):
        category, text = ASSISTANT_ERRORS[assistant_code]
        code = assistant_code
    else:
        if group:
            code, category, text = kind, group, GROUP_MESSAGES[group]
        elif kind is not None:
            code, category = 'unrecognizedNativeKind', 'unknown'
        elif number in (401, 403):
            code, category, text = 'nativeAccessDenied', 'authentication', 'Claude rejected the original account or model access.'
        elif number in (402, 429):
            code, category, text = 'nativeUsageDeclined', 'quota', 'Claude declined this request because of its subscription or usage limits.'
        elif number in (502, 503, 504):
            code, category = 'nativeServiceUnavailable', 'server'
            text = {502: 'Claude model gateway unavailable.', 503: 'Claude model service unavailable.',
                    504: 'Claude model gateway timed out.'}[number]
        elif number is not None and number >= 500:
            code, category, text = 'nativeServerError', 'server', 'Claude reported a server error.'
        elif number is not None and number >= 400:
            code, category, text = 'nativeRequestDeclined', 'request', 'Claude rejected the original request.'
        elif kind is None and assistant_code in ('server_error', 'overloaded'):
            code, category = assistant_code, 'server'
            text = ('Claude reported a server error.' if assistant_code == 'server_error'
                    else 'Claude reports temporary overload.')
    if number is not None:
        text = text.rstrip('.') + f' (HTTP{number}).'
    observation = wire_observation(value.get('wireObservation'))
    return {'source': SOURCE, 'code': code, 'category': category, 'httpStatusCode': number,
            'transientCandidate': category == 'server' and number in (502, 503, 504),
            'nativeKind': kind if group else 'unrecognized' if kind is not None else None,
            'origin': 'first_party' if value.get('origin') == 'first_party' else None,
            'serverCodePresent': value.get('serverCodePresent') if type(value.get('serverCodePresent')) is bool else None,
            'nativeRetryObserved': native_retry is True, 'responseBoundary': 'unqualified',
            'wireObservation': observation, 'retryAllowed': False, 'text': text}


def retry_notice(value):
    value = value if (isinstance(value, dict) and type(value.get('schema')) is int
                      and value.get('schema') == 1 and value.get('source') == RETRY_SOURCE) else {}
    number = status(value.get('httpStatusCode'))
    attempt, maximum, delay = value.get('attempt'), value.get('maxRetries'), value.get('delayMs')
    attempt = attempt if type(attempt) is int and 1 <= attempt <= 65535 else None
    maximum = maximum if type(maximum) is int and 0 <= maximum <= 65535 else None
    delay = delay if type(delay) is int and 0 <= delay <= 3600000 else None
    text = 'The native Claude query reported an internal retry'
    if number is not None:
        text += f' (HTTP{number})'
    text += '. Studio has not started an additional attempt.'
    return {'source': RETRY_SOURCE, 'httpStatusCode': number, 'attempt': attempt, 'maxRetries': maximum,
            'delayMs': delay, 'retryAllowed': False, 'text': text}
