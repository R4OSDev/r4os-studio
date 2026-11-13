"""Direct Messages wire format and signed content; no Claude agent SDK."""
import re
from model_transport import (
    ModelFault, ResponseRejected, completed_response_text, dumps, loads, response_json, response_text, tool_arguments, valid_call_id,
)


def request(binding, messages, instructions, tools, effort):
    wire = []; pending = set()
    from studio_media import image
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
                name = 'mcp_'+part['name'] if binding.get('kind') == 'claude-plan' else part['name']
                content.append({'type': 'tool_use', 'id': part['callId'], 'name': name, 'input': part['arguments']})
                pending.add(part['callId'])
            elif part['type'] == 'tool_result':
                if role != 'user' or part['callId'] not in pending: raise ModelFault('model_context_unpaired')
                pending.remove(part['callId'])
                content.append({'type': 'tool_result', 'tool_use_id': part['callId'], 'content': dumps(part['result']),
                                'is_error': part['result'].get('success') is False})
            elif part['type']=='image':
                if message['role']=='tool' and content and content[-1]['type']=='tool_result':
                    original=content[-1]['content']
                    if isinstance(original,str):content[-1]['content']=[{'type':'text','text':original}]
                    content[-1]['content'].append(image(part,'messages'))
                elif role=='user' and not pending:content.append(image(part,'messages'))
                else:raise ModelFault('model_context_unpaired')
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
        if binding.get('kind') == 'zai-coding-plan':
            value['thinking'] = {'type': 'enabled'}
        else:
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
        self.aliases = {'mcp_'+name: name for name in self.names} if binding.get('kind') == 'claude-plan' else {}
        self.started = False; self.done = False; self.blocks = {}; self.stopped = set()
        self.fragments = {}; self.pending = {}; self.stop_reason = None; self.usage = {}; self.origin = {}; self.extensions = []
        self.output_seen = False

    def push(self, raw):
        if raw == '[DONE]':
            if not self.done: raise ModelFault('model_stream_incomplete')
            return []
        value = response_json(raw)
        kind = value.get('type')
        if kind == 'ping': return []
        if self.done:
            raise ResponseRejected('model_event_after_finish', 'Messages sent an event after message_stop.')
        if kind == 'error':
            error = value.get('error', {})
            raise ModelFault(error.get('type', 'model_provider_error') if isinstance(error, dict) else 'model_provider_error')
        if kind == 'message_start':
            message = value.get('message')
            if self.started or not isinstance(message, dict) or message.get('role') != 'assistant' or message.get('content'):
                raise ResponseRejected('model_invalid_message_start', 'Messages sent a duplicate or invalid assistant start event.')
            self.started = True
            self.origin = {'providerResponseId': message.get('id'), 'reportedModel': message.get('model')}
            usage = message.get('usage')
            if usage is not None:
                if not isinstance(usage, dict):
                    raise ResponseRejected('model_invalid_usage', 'Messages usage must be an object.', usage_unconfirmed=True)
                self.usage.update(usage)
                self.output_seen = bool(usage.get('output_tokens'))
            return []
        if not self.started:
            raise ResponseRejected('model_invalid_message_start', 'Messages sent content before the assistant start event.')
        self.output_seen = True
        if kind == 'message_delta':
            delta = value.get('delta')
            if not isinstance(delta, dict):
                raise ResponseRejected('model_invalid_response_event', 'A Messages delta must be an object.')
            reason = delta.get('stop_reason')
            if reason is not None:
                if self.stop_reason is not None and self.stop_reason != reason:
                    raise ResponseRejected('model_finish_conflict', 'Messages sent conflicting stop reasons.')
                self.stop_reason = reason
            usage = value.get('usage')
            if usage is not None:
                if not isinstance(usage, dict):
                    raise ResponseRejected('model_invalid_usage', 'Messages usage must be an object.', usage_unconfirmed=True)
                self.usage.update(usage)  # Actual cumulative counters, never a sum.
            return []
        if kind == 'message_stop':
            if self.stop_reason is None:
                raise ResponseRejected('model_finish_unavailable', 'Messages ended without a stop reason.')
            if len(self.stopped) != len(self.blocks):
                raise ResponseRejected('model_invalid_content_block', 'Messages ended before closing every content block.')
            self.done = True; return []
        if kind == 'content_block_start':
            index, block = value.get('index'), value.get('content_block')
            if type(index) is not int or not 0 <= index < 8192 or index in self.blocks or not isinstance(block, dict):
                raise ResponseRejected('model_invalid_content_block', 'Messages sent a content block with a duplicate or invalid index or value.')
            if block.get('type') not in ('text', 'thinking', 'redacted_thinking', 'tool_use'):
                raise ResponseRejected('model_content_unavailable', 'Messages sent an unsupported content block type.')
            fields = ('text',) if block['type'] == 'text' else ('thinking', 'signature') if block['type'] == 'thinking' else ()
            if any(not isinstance(block.get(field, ''), str) for field in fields):
                raise ResponseRejected('model_invalid_content_block', 'A Messages content block has a non-text field where text is required.')
            self.blocks[index] = dict(block)
            return []
        if kind in ('content_block_delta', 'content_block_stop'):
            index = value.get('index')
            if type(index) is not int or index not in self.blocks or index in self.stopped:
                raise ResponseRejected('model_invalid_content_block', 'A Messages delta or stop event refers to an absent or closed block.')
            block = self.blocks[index]
            if kind == 'content_block_stop':
                if index in self.fragments:
                    if block.get('input'):
                        raise ResponseRejected('model_tool_input_conflict', 'Messages sent both original and streamed input for a tool call.')
                    block['input'] = tool_arguments(completed_response_text(self.fragments[index]))
                if self.pending.get(index):
                    raise ResponseRejected('model_stream_invalid', 'A Messages content block ended with an incomplete Unicode character.')
                self.stopped.add(index); return []
            delta = value.get('delta')
            if not isinstance(delta, dict):
                raise ResponseRejected('model_invalid_response_event', 'A Messages content block delta must be an object.')
            mapping = {'text_delta': ('text', 'text', 'text'), 'thinking_delta': ('thinking', 'thinking', 'reasoning')}
            if delta.get('type') in mapping:
                expected, field, channel = mapping[delta['type']]
                if block['type'] != expected:
                    raise ResponseRejected('model_invalid_content_block', 'A Messages delta does not match its content block type.')
                text, self.pending[index] = response_text(delta.get(field), self.pending.get(index, ''))
                block[field] = block.get(field, '') + text
                return [(channel, text)] if text else []
            if delta.get('type') == 'signature_delta':
                if block['type'] != 'thinking' or not isinstance(delta.get('signature'), str):
                    raise ResponseRejected('model_invalid_signature', 'Messages sent a signature outside a thinking block or with an invalid type.')
                block['signature'] = block.get('signature', '') + delta['signature']
            elif delta.get('type') == 'input_json_delta':
                fragment = delta.get('partial_json')
                if block['type'] != 'tool_use' or not isinstance(fragment, str):
                    raise ResponseRejected('model_invalid_tool_arguments', 'A Messages tool input fragment has the wrong block or value type.')
                if not fragment: return []
                self.fragments[index] = self.fragments.get(index, '') + fragment
                if len(self.fragments[index].encode('utf-8', 'surrogatepass')) > 131072:
                    raise ResponseRejected('model_invalid_tool_arguments', 'Messages tool arguments exceeded the supported size.')
            elif delta.get('type') == 'citations_delta':
                block.setdefault('citations', []).append(delta.get('citation'))
            else:
                if block['type'] == 'tool_use':
                    raise ResponseRejected('model_tool_delta_unavailable', 'Messages sent an unsupported tool input delta.')
                self.extensions.append(value)
            return []
        self.extensions.append(value)
        return []

    def result(self):
        if not self.done: raise ModelFault('model_stream_incomplete')
        if sorted(self.blocks) != list(range(len(self.blocks))):
            raise ResponseRejected('model_invalid_content_block', 'The completed Messages blocks have noncontiguous indexes.')
        if self.stop_reason == 'max_tokens':
            raise ModelFault('model_output_limit')
        if self.stop_reason not in ('end_turn', 'stop_sequence', 'tool_use', 'refusal'):
            raise ResponseRejected('model_finish_unavailable', 'Messages sent an unsupported stop reason.')
        blocks = [self.blocks[index] for index in range(len(self.blocks))]
        content = []; calls = set()
        for block in blocks:
            if block['type'] == 'text':
                content.append({'type': 'text', 'text': completed_response_text(block.get('text', ''))})
            elif block['type'] == 'tool_use':
                ident = block.get('id')
                wire_name = block.get('name')
                name = (self.aliases.get(wire_name) if self.binding.get('kind') == 'claude-plan' else wire_name) if isinstance(wire_name, str) else None
                if (not valid_call_id(ident) or ident in calls or len(calls) >= 32 or name not in self.names
                        or not isinstance(block.get('input'), dict)):
                    raise ResponseRejected('model_invalid_tool_call', 'Messages sent an invalid or undeclared tool call.')
                calls.add(ident)
                content.append({'type': 'tool_call', 'callId': ident, 'name': name, 'arguments': block['input']})
            elif block['type'] == 'thinking':
                if self.binding.get('kind') != 'zai-coding-plan' and (not isinstance(block.get('signature'), str) or not block['signature']):
                    raise ResponseRejected('model_reasoning_incomplete', 'A Messages thinking block has no signature.')
        if (self.stop_reason == 'tool_use') != bool(calls):
            raise ResponseRejected('model_tool_finish_mismatch', 'The Messages stop reason disagrees with the tool calls.')
        content.append({'type': 'provider', 'protocol': 'messages', 'value': dumps(blocks)})
        return {'content': content, 'origin': {**self.origin, **({'extensionDeltas': self.extensions} if self.extensions else {})},
                'usage': self.usage or None, 'finishReason': self.stop_reason}
