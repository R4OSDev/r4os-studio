"""Direct Messages wire format and signed content; no Claude agent SDK."""
import re
from model_transport import ModelFault, dumps, loads, text_fragment, unicode_text


def request(binding, messages, instructions, tools, effort):
    wire = []; pending = set()
    for message in messages:
        originals = [p for p in message['content'] if p['type'] == 'provider']
        if originals:
            origin = message.get('origin', {}).get('selection', {})
            if (len(originals) != 1 or originals[0]['protocol'] != 'messages'
                    or origin.get('providerId') != binding['id'] or origin.get('model') != binding['model'] or pending):
                raise ModelFault('model_context_not_portable')
            content = loads(originals[0]['value'])
            if not isinstance(content, list): raise ModelFault()
            wire.append({'role': 'assistant', 'content': content})
            pending.update(p['id'] for p in content if p.get('type') == 'tool_use')
            continue
        content = []; role = 'user' if message['role'] == 'tool' else message['role']
        if role not in ('user', 'assistant'): raise ModelFault('model_role_unavailable')
        if pending and role == 'assistant': raise ModelFault('model_context_unpaired')
        for part in message['content']:
            if part['type'] == 'text':
                if pending and role != 'assistant': raise ModelFault('model_context_unpaired')
                content.append({'type': 'text', 'text': part['text']})
            elif part['type'] == 'tool_call':
                if role != 'assistant' or part['callId'] in pending: raise ModelFault('model_context_unpaired')
                content.append({'type': 'tool_use', 'id': part['callId'], 'name': part['name'], 'input': part['arguments']})
                pending.add(part['callId'])
            elif part['type'] == 'tool_result':
                if role != 'user' or part['callId'] not in pending: raise ModelFault('model_context_unpaired')
                pending.remove(part['callId'])
                content.append({'type': 'tool_result', 'tool_use_id': part['callId'], 'content': dumps(part['result']),
                                'is_error': part['result'].get('success') is False})
            else:
                raise ModelFault('model_content_unavailable')
        if wire and wire[-1]['role'] == role: wire[-1]['content'].extend(content)
        else: wire.append({'role': role, 'content': content})
    if pending: raise ModelFault('model_context_unpaired')
    maximum = binding.get('maxOutputTokens', 8192)
    if type(maximum) is not int or maximum < 1: raise ModelFault('model_output_budget_unavailable')
    value = {'model': binding['model'], 'system': instructions, 'messages': wire, 'max_tokens': maximum,
             'stream': True, 'tools': [{'name': tool['name'], 'description': tool.get('description', ''),
                                       'input_schema': tool['inputSchema']} for tool in tools]}
    if effort and effort != 'none': value['output_config'] = {'effort': effort}
    thinking = binding.get('thinkingType')
    if thinking == 'adaptive':
        value['thinking'] = {'type': 'adaptive'}
    elif thinking == 'enabled':
        budget = binding.get('thinkingBudget')
        if type(budget) is not int or budget < 1024 or budget >= maximum: raise ModelFault('model_thinking_budget_unavailable')
        value['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
    elif thinking is not None:
        raise ModelFault('model_thinking_unavailable')
    if effort == 'none' and binding.get('reasoning') != 'unsupported':
        if binding.get('thinkingDisabled') is not True: raise ModelFault('model_thinking_unavailable')
        value['thinking'] = {'type': 'disabled'}
    version = binding.get('apiVersion', '2026-10-21')
    if not isinstance(version, str) or not re.fullmatch(r'\d{4}-\d\d-\d\d', version): raise ModelFault('model_api_version_invalid')
    return value, {'anthropic-version': version}


class Messages:
    def __init__(self, binding, tools):
        self.binding = binding; self.names = {tool['name'] for tool in tools}
        self.started = False; self.done = False; self.blocks = {}; self.stopped = set()
        self.fragments = {}; self.pending = {}; self.stop_reason = None; self.usage = {}; self.origin = {}; self.extensions = []

    def push(self, raw):
        if raw == '[DONE]':
            if not self.done: raise ModelFault('model_stream_incomplete')
            return []
        value = loads(raw)
        if not isinstance(value, dict): raise ModelFault()
        kind = value.get('type')
        if kind == 'ping': return []
        if self.done: raise ModelFault()
        if kind == 'error':
            error = value.get('error', {})
            raise ModelFault(error.get('type', 'model_provider_error') if isinstance(error, dict) else 'model_provider_error')
        if kind == 'message_start':
            message = value.get('message')
            if self.started or not isinstance(message, dict) or message.get('role') != 'assistant' or message.get('content'):
                raise ModelFault()
            self.started = True
            self.origin = {'providerResponseId': message.get('id'), 'reportedModel': message.get('model')}
            usage = message.get('usage')
            if usage is not None:
                if not isinstance(usage, dict): raise ModelFault()
                self.usage.update(usage)
            return []
        if not self.started: raise ModelFault()
        if kind == 'message_delta':
            delta = value.get('delta')
            if not isinstance(delta, dict): raise ModelFault()
            reason = delta.get('stop_reason')
            if reason is not None:
                if self.stop_reason is not None and self.stop_reason != reason: raise ModelFault()
                self.stop_reason = reason
            usage = value.get('usage')
            if usage is not None:
                if not isinstance(usage, dict): raise ModelFault()
                self.usage.update(usage)  # Actual cumulative counters, never a sum.
            return []
        if kind == 'message_stop':
            if self.stop_reason is None or len(self.stopped) != len(self.blocks): raise ModelFault('model_stream_incomplete')
            self.done = True; return []
        if kind == 'content_block_start':
            index, block = value.get('index'), value.get('content_block')
            if type(index) is not int or not 0 <= index < 8192 or index in self.blocks or not isinstance(block, dict): raise ModelFault()
            if block.get('type') not in ('text', 'thinking', 'redacted_thinking', 'tool_use'): raise ModelFault('model_content_unavailable')
            fields = ('text',) if block['type'] == 'text' else ('thinking', 'signature') if block['type'] == 'thinking' else ()
            if any(not isinstance(block.get(field, ''), str) for field in fields): raise ModelFault()
            self.blocks[index] = dict(block)
            return []
        if kind in ('content_block_delta', 'content_block_stop'):
            index = value.get('index')
            if type(index) is not int or index not in self.blocks or index in self.stopped: raise ModelFault()
            block = self.blocks[index]
            if kind == 'content_block_stop':
                if index in self.fragments:
                    if block.get('input'): raise ModelFault('model_tool_input_conflict')
                    block['input'] = loads(unicode_text(self.fragments[index]))
                if self.pending.get(index): raise ModelFault('model_stream_invalid')
                self.stopped.add(index); return []
            delta = value.get('delta')
            if not isinstance(delta, dict): raise ModelFault()
            mapping = {'text_delta': ('text', 'text', 'text'), 'thinking_delta': ('thinking', 'thinking', 'reasoning')}
            if delta.get('type') in mapping:
                expected, field, channel = mapping[delta['type']]
                if block['type'] != expected: raise ModelFault()
                text, self.pending[index] = text_fragment(delta.get(field), self.pending.get(index, ''))
                block[field] = block.get(field, '') + text
                return [(channel, text)] if text else []
            if delta.get('type') == 'signature_delta':
                if block['type'] != 'thinking' or not isinstance(delta.get('signature'), str): raise ModelFault()
                block['signature'] = block.get('signature', '') + delta['signature']
            elif delta.get('type') == 'input_json_delta':
                if block['type'] != 'tool_use' or not isinstance(delta.get('partial_json'), str): raise ModelFault()
                self.fragments[index] = self.fragments.get(index, '') + delta['partial_json']
                if len(self.fragments[index].encode('utf-8', 'surrogatepass')) > 131072: raise ModelFault('model_invalid_tool_arguments')
            elif delta.get('type') == 'citations_delta':
                block.setdefault('citations', []).append(delta.get('citation'))
            else:
                if block['type'] == 'tool_use': raise ModelFault('model_tool_delta_unavailable')
                self.extensions.append(value)
            return []
        self.extensions.append(value)
        return []

    def result(self):
        if not self.done or sorted(self.blocks) != list(range(len(self.blocks))): raise ModelFault('model_stream_incomplete')
        if self.stop_reason not in ('end_turn', 'stop_sequence', 'tool_use', 'refusal'):
            raise ModelFault('model_output_limit' if self.stop_reason == 'max_tokens' else 'model_finish_unavailable')
        blocks = [self.blocks[index] for index in range(len(self.blocks))]
        content = []; calls = set()
        for block in blocks:
            if block['type'] == 'text':
                content.append({'type': 'text', 'text': unicode_text(block.get('text', ''))})
            elif block['type'] == 'tool_use':
                ident = block.get('id')
                if (not isinstance(ident, str) or not 1 <= len(ident.encode()) <= 256 or ident in calls or len(calls) >= 32
                        or any(ord(c) < 33 or ord(c) == 127 for c in ident) or block.get('name') not in self.names
                        or not isinstance(block.get('input'), dict)): raise ModelFault('model_invalid_tool_call')
                calls.add(ident)
                content.append({'type': 'tool_call', 'callId': ident, 'name': block['name'], 'arguments': block['input']})
            elif block['type'] == 'thinking':
                if not isinstance(block.get('signature'), str) or not block['signature']: raise ModelFault('model_reasoning_incomplete')
        if (self.stop_reason == 'tool_use') != bool(calls): raise ModelFault()
        content.append({'type': 'provider', 'protocol': 'messages', 'value': dumps(blocks)})
        return {'content': content, 'origin': {**self.origin, **({'extensionDeltas': self.extensions} if self.extensions else {})},
                'usage': self.usage or None, 'finishReason': self.stop_reason}
