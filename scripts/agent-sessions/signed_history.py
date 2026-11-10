"""Preserve the exact Messages prefix before replayed signed reasoning."""
import hashlib

from model_transport import ModelFault, dumps, loads


def protected_route(binding):
    # Unknown Messages connectors may use the same signed-history contract.
    return binding.get('protocol') == 'messages' and binding.get('kind') != 'zai-coding-plan'


def signed(blocks):
    return isinstance(blocks, list) and any(
        block.get('type') == 'redacted_thinking' or block.get('type') == 'thinking' and block.get('signature')
        for block in blocks if isinstance(block, dict))


def latest(messages, binding):
    from portable_history import foreign_selection
    if binding.get('protocol') != 'messages':
        return None
    for record in reversed(messages):
        if record['role'] == 'assistant' and not foreign_selection(record.get('origin', {}).get('selection', {}), binding):
            for part in record['content']:
                if part['type'] == 'provider' and part.get('protocol') == 'messages' and signed(loads(part['value'])):
                    return record
    return None


def prefix(body, count):
    return hashlib.sha256(dumps([body.get('system'), body.get('tools'), body['messages'][:count]]).encode()).hexdigest()


class Prefix:
    def __init__(self, store, sid, binding):
        self.store = store
        self.sid = sid
        self.binding = binding
        self.record = None
        self.proof = None

    def check(self, messages, body):
        record = latest(messages, self.binding)
        if record is None:
            return
        rid = record.get('origin', {}).get('studioRequestId')
        if self.record != rid or self.proof is None:
            from history_receipts import original_input
            original = original_input(self.store, self.sid, record)
            self.record = rid
            self.proof = (len(original['messages']), prefix(original, len(original['messages']))) if (
                isinstance(original, dict) and isinstance(original.get('messages'), list)) else None
        wire = body['messages']
        position = next((i for i in range(len(wire) - 1, -1, -1)
                         if wire[i]['role'] == 'assistant' and signed(wire[i]['content'])), None)
        if self.proof is None or position != self.proof[0] or prefix(body, position) != self.proof[1]:
            raise ModelFault('context_signed_prefix', not_dispatched=True)
