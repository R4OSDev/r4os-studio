"""Private direct model transport; connectors never run tools or continuations."""
import asyncio
import base64
import codecs
import json
import re
import hashlib
from pathlib import Path

from api_endpoint import resolve_binding
from store import ProjectFault


class ModelFault(ProjectFault):
    def __init__(self, code='model_protocol_error', http_status=None, *, not_dispatched=False, details=None):
        messages = {401: 'The provider credential was rejected.', 402: 'The API account needs credits or billing attention.',
                    403: 'The account cannot access the selected model.', 404: 'The selected model or API route was not found.',
                    429: 'The model service is rate or usage limited.'}
        message = messages.get(http_status, 'The model response could not be confirmed. It was not repeated.')
        super().__init__(message, 503)
        self.code = code
        self.http_status = http_status
        self.not_dispatched=not_dispatched;self.details=details
        self.category=('connection' if not_dispatched and http_status is None else 'authentication' if http_status==401 else 'access' if http_status in (403,404)
            else 'billing' if http_status==402 else 'quota' if str(code) in ('insufficient_quota','quota_exceeded','zai_subscription_exhausted','subscription_sharing_usage_limit_exceeded')
            else 'rate' if http_status==429 else 'context' if http_status==413 or code in ('context_length_exceeded','context_window_exceeded','prompt_too_long','model_input_limit')
            else 'outputLimit' if code=='model_output_limit' else 'service' if http_status and http_status>=500 or code in ('overloaded_error','server_error')
            else 'incomplete' if code in ('model_stream_incomplete','model_response_incomplete','model_transport_timeout','model_connection_error','model_transport_error') else 'protocol')
        if code in ('subscription_sharing_usage_unavailable','subscription_sharing_user_unavailable'):self.category='service'
        if code=='subscription_sharing_invalid_user':self.category='authentication'
        if code in ('subscription_sharing_user_not_eligible','subscription_sharing_route_not_supported','chatpass_v2_scope_not_authorized','chatpass_v2_invalid_authorization_context'):self.category='access'
        if str(code).startswith('subscription_sharing_'):
            self.args=('ChatGPT plan use was not confirmed. Review this connection and its actual ChatGPT usage settings; no alternate billing route was used.',)
        if self.category=='context':self.args=('The selected model rejected the context size. Original history was preserved.',)
        if self.category=='connection':self.args=('The connection failed before the model request was sent.',)
        if code=='claude_subscription_unavailable':
            self.category='quota'
            self.args=('Refresh this Claude connection’s subscription limits to confirm included usage and disabled paid extra usage. No model request was sent.',)
        if code=='model_tool_schema_unavailable':
            self.category='protocol'
            self.args=('A Studio tool schema cannot be represented for this model. No model request was sent.',)
        if code=='model_tool_schema_rejected':
            self.category='protocol'
            self.args=('The model service rejected a Studio tool input schema. The request was not repeated.',)
        if code in ('context_retained_limit','context_compaction_bound'):
            self.category='context'
            self.args=('The context could not be reduced safely within its limits. Current and unresolved tool observations were preserved. No further model request was sent.',)
        if code in ('context_input_limit','context_input_unavailable'):
            self.category='context'
            self.args=(('The complete provider input exceeds the effective input limit. Reduce the current input or review the session limit. Original history was preserved; no model request was sent.' if code=='context_input_limit' else
                'The complete provider input could not be checked against its limit. Original history was preserved; no model request was sent.'),)
        if not isinstance(code,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',code):self.code='model_provider_error'


def loads(value, *, allow_identical_duplicates=False):
    """Keep envelopes strict; tool arguments may repeat an identical JSON value."""
    def invalid(_value):
        raise ValueError('Nonfinite model value')
    try:
        def unique(pairs):
            result = {}
            for key, part in pairs:
                if key in result:
                    if not allow_identical_duplicates or json.dumps(result[key], sort_keys=True, allow_nan=False) != json.dumps(part, sort_keys=True, allow_nan=False):
                        raise ValueError('Duplicate model field')
                result[key] = part
            return result
        return json.loads(value, parse_constant=invalid, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError):
        raise ModelFault() from None


def dumps(value):
    try:
        result = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        result.encode('utf-8')
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ModelFault('model_input_invalid') from None


def text_fragment(value, pending=''):
    if not isinstance(value, str): raise ModelFault('model_stream_invalid')
    text = pending + value; pending = ''
    if text and 0xd800 <= ord(text[-1]) <= 0xdbff: pending = text[-1]; text = text[:-1]
    try: return text.encode('utf-16-le', 'surrogatepass').decode('utf-16-le'), pending
    except UnicodeError: raise ModelFault('model_stream_invalid') from None


def unicode_text(value):
    text, pending = text_fragment(value)
    if pending: raise ModelFault('model_stream_invalid')
    return text


class SSE:
    """One bounded UTF-8/SSE decoder shared by every wire protocol."""
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8')('strict')
        self.buffer = ''; self.data = []; self.size = 0
        self.started = False

    def push(self, chunk, final=False):
        try:
            text = self.decoder.decode(chunk, final)
            if not self.started and text:
                text = text.removeprefix('\ufeff'); self.started = True
            self.buffer += text
        except UnicodeError:
            raise ModelFault('model_stream_invalid') from None
        events = []
        while True:
            positions = [i for i in (self.buffer.find('\r'), self.buffer.find('\n')) if i >= 0]
            if not positions:
                break
            index = min(positions)
            if not final and self.buffer[index:] == '\r':
                break
            width = 2 if self.buffer[index:index+2] == '\r\n' else 1
            line, self.buffer = self.buffer[:index], self.buffer[index+width:]
            if len(line.encode()) > 16 * 1024 * 1024:
                raise ModelFault('model_stream_limit')
            if not line:
                if self.data:
                    events.append('\n'.join(self.data)); self.data = []; self.size = 0
            elif line.startswith('data:'):
                value = line[5:]
                if value.startswith(' '): value = value[1:]
                self.size += len(value.encode())
                if self.size > 16 * 1024 * 1024:
                    raise ModelFault('model_stream_limit')
                self.data.append(value)
        if len(self.buffer.encode()) > 16 * 1024 * 1024 or final and (self.buffer or self.data):
            raise ModelFault('model_stream_incomplete')
        return events


class ModelTransport:
    def __init__(self, binding, model, credential=None, headers=None, chat_policy=None, client=None):
        self.binding = {**binding, 'model': model}
        self.credential = credential
        self.headers = headers or {}
        self.chat_policy = chat_policy or {}
        self.client = client
        self.child = None
        self.closed_confirmed = True
        self.attempted = False
        self.capture_observer = None
        self.request_observer = None
        self.process_observer = None
        self.event_observer = None
        self.flush_observer = None
        self.flush_delay = None
        self.request_sha256 = None
        self.media_resolver = None
        self.history_resolver = None
        self.history_scope = ()
        self._frozen = None
        self.context_policy = None
        self._input_estimate = None

    def parser(self, tools):
        protocol = self.binding['protocol']
        if protocol == 'responses':
            from model_responses import Responses
            return Responses(self.binding, tools)
        if protocol == 'chat-completions':
            from model_chat import Chat
            return Chat(self.binding, tools)
        if protocol == 'messages':
            from model_messages import Messages
            return Messages(self.binding, tools)
        raise ModelFault('model_protocol_unavailable')

    def decoder(self):
        return SSE()

    def freeze_scope(self):
        return (dumps([self.binding,self.chat_policy,self.client,self.headers,self.context_policy]), self.credential,
                self.history_resolver, self.history_scope)

    def freeze(self, messages, instructions, tools, effort='', *, retain=True):
        # Used only for an immutable active worker snapshot. At most one bounded
        # request and its resolved media survive estimation until dispatch.
        body, parser = self.prepare(messages, instructions, tools, effort)
        raw = self.encoded(body)
        if retain and len(raw.encode()) <= 8*1024*1024:
            self._frozen = {'messages':messages, 'instructions':instructions, 'tools':dumps(tools),
                            'effort':effort, 'body':body, 'raw':raw, 'scope':self.freeze_scope()}
        else: self._frozen = None
        return body, parser

    def encoded(self, body):
        return self._frozen['raw'] if self._frozen is not None and self._frozen['body'] is body else dumps(body)

    def input_estimate(self,body):
        raw=self.encoded(body)
        if self._input_estimate is None or self._input_estimate[0]!=raw:
            from input_budget import estimate
            self._input_estimate=(raw,estimate(raw))
        return self._input_estimate[1]

    def check_input(self,body):
        from input_budget import strict,limit
        if not strict(self.context_policy):return
        binding=self.binding.copy()
        for key in ('max_output_tokens','max_completion_tokens','max_tokens'):
            if type(body.get(key)) is int and body[key]>0:binding['maxOutputTokens']=body[key];break
        value=self.input_estimate(body);maximum=limit(self.context_policy,binding)
        if maximum is not None and value['tokens']>maximum:
            raise ModelFault('context_input_limit',not_dispatched=True,
                details={'inputEstimate':value['tokens'],'inputLimit':maximum,'method':value['method']})

    def prepare(self, messages, instructions, tools, effort=''):
        recoveries = self.history_resolver(messages) if self.history_resolver else {}
        self.history_scope = tuple(sorted((key, dumps(value)) for key, value in recoveries.items()))
        frozen = self._frozen
        if frozen is not None and frozen['scope'] == self.freeze_scope() and frozen['messages'] is messages and frozen['instructions'] == instructions and frozen['tools'] == dumps(tools) and frozen['effort'] == effort:
            return frozen['body'], self.parser(tools)  # Parser state belongs to this one attempt.
        from portable_history import project
        messages = project(messages, self.binding, recoveries)
        if any(p['type'] in ('image','document') for m in messages for p in m['content']):
            from studio_media import resolve
            messages=resolve(messages,self.media_resolver)
        if self.binding['protocol'] == 'responses':
            from model_responses import request
            body = request(self.binding, messages, instructions, tools, effort)
        elif self.binding['protocol'] == 'chat-completions':
            from model_chat import request
            body, headers = request(self.binding, messages, instructions, tools, effort, self.chat_policy, self.client)
            self.headers = {**self.headers, **headers}
        elif self.binding['protocol'] == 'messages':
            from model_messages import request
            body, headers = request(self.binding, messages, instructions, tools, effort)
            self.headers = {**self.headers, **headers}
            if self.binding['kind'] == 'claude-plan':
                from claude_wire import request as oauth_request, headers as oauth_headers
                body = oauth_request(body, tools)
                self.headers = {**self.headers, **oauth_headers()}
            if self.binding['kind'] == 'zai-coding-plan':
                from zai_policy import require
                from zai_client import headers as client_headers
                require(self.binding)
                self.headers = {**self.headers, **client_headers(self.client)}
        else:
            raise ModelFault('model_protocol_unavailable')
        return body, self.parser(tools)

    async def response(self, messages, instructions, tools, effort='', on_text=None, on_reasoning=None):
        if self.child is not None: raise ModelFault('model_request_busy')
        self.attempted = False; self.request_sha256 = None
        body, parser = self.prepare(messages, instructions, tools, effort)
        try:
            await self.send(body, parser, on_text, on_reasoning)
            return parser.result()
        except ModelFault as error:
            error.partial={'origin':getattr(parser,'origin',None),'usage':getattr(parser,'usage',None)}
            if self.credential and self.credential in str(error.code): error.code = 'model_provider_error'
            raise

    async def send(self, body, parser, on_text=None, on_reasoning=None):
        if self.child is not None:
            raise ModelFault('model_request_busy')
        if self._frozen is not None and self._frozen['body'] is body and self._frozen['scope'] != self.freeze_scope():
            raise ModelFault('model_request_selection_changed', not_dispatched=True)
        raw_body = self.encoded(body)
        self.request_sha256=hashlib.sha256(raw_body.encode()).hexdigest()
        if len(raw_body.encode()) > 8 * 1024 * 1024:
            raise ModelFault('model_input_limit',not_dispatched=True)
        self.check_input(body)
        if self.capture_observer:self.capture_observer(raw_body,self.binding,self.context_policy,
            self._input_estimate[1] if self._input_estimate is not None and self._input_estimate[0]==raw_body else None)
        addresses = await resolve_binding(self.binding)
        bootstrap = dumps({'binding': self.binding, 'addresses': addresses, 'key': self.credential,
                           'body': raw_body, 'extraHeaders': self.headers}).encode()
        ended = False; decoder = self.decoder()
        try:
            self.child = await asyncio.create_subprocess_exec('/usr/bin/node', str(Path(__file__).with_name('model_http.mjs')),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=262144, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            self.closed_confirmed = False
            if self.process_observer:self.process_observer('started',self.child)
            self.attempted = True
            self.child.stdin.write(bootstrap)
            await self.child.stdin.drain()
            self.child.stdin.close()
            while True:
                delay=self.flush_delay() if self.flush_delay else None
                try:
                    raw=await asyncio.wait_for(self.child.stdout.readline(),max(0.001,delay)) if delay is not None else await self.child.stdout.readline()
                except asyncio.TimeoutError:
                    self.flush_observer()
                    continue
                if not raw:break
                frame = loads(raw)
                if not isinstance(frame, dict): raise ModelFault()
                if frame.get('type') in ('dispatch','response'):
                    if self.request_observer:self.request_observer(frame['type'],frame.get('httpStatus'))
                    continue
                if frame.get('type') == 'error':
                    code = frame.get('code', 'model_transport_error')
                    if self.binding.get('kind') == 'claude-plan':
                        from claude_tool_schema import rejected
                        if rejected(frame.get('httpStatus'), frame.get('details')): code = 'model_tool_schema_rejected'
                    error = ModelFault(code, frame.get('httpStatus'),
                        not_dispatched=frame.get('notDispatched') is True,details=frame.get('details'))
                    if (self.binding.get('kind') == 'zai-coding-plan' and frame.get('httpStatus') == 400 and str(code) == '1261'
                            and isinstance(error.details, dict) and error.details.get('httpResponseComplete') is True):
                        error.category='context'
                        error.args=('Z.AI rejected the prompt because it exceeds the model context limit. Original history was preserved; the request was not repeated.',)
                    raise error
                if frame.get('type') == 'end':
                    if ended: raise ModelFault()
                    ended = True
                    values = decoder.push(b'', True)
                elif frame.get('type') == 'bytes' and not ended:
                    try: chunk = base64.b64decode(frame['value'], validate=True)
                    except (ValueError, TypeError): raise ModelFault() from None
                    values = decoder.push(chunk)
                else:
                    raise ModelFault()
                for value in values:
                    if self.event_observer:self.event_observer(value)
                    for channel, text in parser.push(value) or []:
                        callback = on_text if channel == 'text' else on_reasoning if channel == 'reasoning' else None
                        if callback is not None: await callback(text)
            if await self.child.wait() != 0 or not ended:
                raise ModelFault('model_stream_incomplete')
        except (OSError, ValueError, ConnectionError) as error:
            raise ModelFault('model_transport_error') from error
        finally:
            try:await self.close()
            finally:
                if self.flush_observer:self.flush_observer()

    async def close(self):
        child = self.child
        if child is None:
            return
        if child.returncode is None:
            try: child.terminate()
            except ProcessLookupError: pass
            try: await asyncio.wait_for(child.wait(), 5)
            except asyncio.TimeoutError:
                try: child.kill()
                except ProcessLookupError: pass
                await child.wait()
        self.closed_confirmed = child.returncode is not None
        if self.process_observer:self.process_observer('ended',child)
        self.child = None
