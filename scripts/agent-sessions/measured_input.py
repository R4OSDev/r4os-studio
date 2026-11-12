"""Calibrate a complete input using a confirmed, exact wire prefix."""
from context_policy import optimized
from history_receipts import original_request
from input_count import members
from model_transport import dumps
from studio_usage import numbers


def reference(raw, metadata, call):
    protocol = metadata['protocol']
    counting = (metadata.get('context') or {}).get('counting') or {}
    reported = numbers(call.get('usage'), protocol)['input']
    local = counting.get('tokens')
    if (reported is None or type(local) is not int
            or not counting.get('bindingSha256') or not counting.get('methodVersion')
            or counting.get('requestSha256') != call.get('requestSha256')):
        return None
    field = 'input' if protocol == 'responses' else 'messages'
    envelope = []
    prefix = None
    items = 0
    for key, start, end, value in members(raw, True):
        if key == field and isinstance(value, list) and value:
            prefix = raw[:end - 1]
            items = len(value)
        else:
            envelope.append((key, raw[start:end]))
    if prefix is None:
        return None
    return {'prefix': prefix, 'items': items, 'envelope': envelope, 'field': field,
            'counting': counting, 'policy': metadata.get('contextPolicy') or {},
            'inputTokens': reported, 'requestId': call['requestId'], 'requestSha256': call['requestSha256']}


def apply(basis, raw, body, local, policy, binding):
    if basis is None or binding.get('kind') == 'openrouter' or type(local.get('tokens')) is not int:
        return
    previous = basis['counting']
    if any(local.get(key) != previous.get(key) for key in ('bindingSha256', 'methodVersion', 'tokenizer', 'source')):
        return
    original_policy = basis['policy']
    if (any(policy.get(key) != original_policy.get(key) for key in ('counting', 'imageEstimate'))
            or any(optimized(policy, version) != optimized(original_policy, version) for version in (2, 7, 8))):
        return
    messages = body.get(basis['field'])
    if not isinstance(messages, list) or len(messages) < basis['items']:
        return
    prefix = basis['prefix']
    boundary = ',' if len(messages) > basis['items'] else ']'
    if not raw.startswith(prefix) or raw[len(prefix):len(prefix)+1] != boundary:
        return
    if [(key, dumps(value)) for key, value in body.items() if key != basis['field']] != basis['envelope']:
        return
    delta = max(0, local['tokens'] - previous['tokens'])
    reserve = max(256, (delta + 9) // 10)
    local['measuredPrefix'] = {'requestId': basis['requestId'], 'requestSha256': basis['requestSha256'],
                               'inputTokens': basis['inputTokens'], 'deltaTokens': delta, 'reserveTokens': reserve,
                               'estimatedTokens': basis['inputTokens'] + delta}


class MeasuredInput:
    def __init__(self, store, session_id):
        self.store = store
        self.session_id = session_id
        self.record = None
        self.request_id = None
        self.loaded = False
        self.basis = None

    def select(self, records):
        record = next((row for row in reversed(records) if row['role'] == 'assistant'
                       and row.get('origin', {}).get('providerResponseId')), None)
        request_id = (record or {}).get('origin', {}).get('studioRequestId')
        if request_id != self.request_id:
            self.record = record
            self.request_id = request_id
            self.loaded = False
            self.basis = None

    def estimate(self, raw, body, local, policy, binding):
        if self.request_id is None or binding.get('kind') == 'openrouter':
            return
        if not self.loaded:
            original = original_request(self.store, self.session_id, self.record)
            if original is not None:
                try:
                    self.basis = reference(*original)
                except (ValueError, TypeError, KeyError, RecursionError):
                    pass
            self.loaded = True
        apply(self.basis, raw, body, local, policy, binding)
