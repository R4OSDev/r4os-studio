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
        if not isinstance(code,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',code):self.code='model_provider_error'


def loads(value):
    def invalid(_value):
        raise ValueError('Nonfinite model value')
    try:
        def unique(pairs):
            result = {}
            for key, part in pairs:
                if key in result: raise ValueError('Duplicate model field')
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
        self.process_observer = None
        self.event_observer = None
        self.request_sha256 = None
        self.media_resolver = None

    def prepare(self, messages, instructions, tools, effort=''):
        from portable_history import native_import
        messages = native_import(messages)
        if any(p['type'] in ('image','document') for m in messages for p in m['content']):
            from studio_media import resolve
            messages=resolve(messages,self.media_resolver)
        if self.binding['protocol'] == 'responses':
            from model_responses import request, Responses
            body = request(self.binding, messages, instructions, tools, effort)
            parser = Responses(self.binding, tools)
        elif self.binding['protocol'] == 'chat-completions':
            from model_chat import request, Chat
            body, headers = request(self.binding, messages, instructions, tools, effort, self.chat_policy, self.client)
            self.headers = {**self.headers, **headers}
            parser = Chat(self.binding, tools)
        elif self.binding['protocol'] == 'messages':
            from model_messages import request, Messages
            body, headers = request(self.binding, messages, instructions, tools, effort)
            self.headers = {**self.headers, **headers}
            parser = Messages(self.binding, tools)
        else:
            raise ModelFault('model_protocol_unavailable')
        return body, parser

    async def response(self, messages, instructions, tools, effort='', on_text=None, on_reasoning=None):
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
        raw_body = dumps(body)
        self.request_sha256=hashlib.sha256(raw_body.encode()).hexdigest()
        if len(raw_body.encode()) > 8 * 1024 * 1024:
            raise ModelFault('model_input_limit')
        addresses = await resolve_binding(self.binding)
        bootstrap = dumps({'binding': self.binding, 'addresses': addresses, 'key': self.credential,
                           'body': raw_body, 'extraHeaders': self.headers}).encode()
        ended = False; decoder = SSE()
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
            while raw := await self.child.stdout.readline():
                frame = loads(raw)
                if not isinstance(frame, dict): raise ModelFault()
                if frame.get('type') == 'error':
                    raise ModelFault(frame.get('code', 'model_transport_error'), frame.get('httpStatus'),
                        not_dispatched=frame.get('notDispatched') is True,details=frame.get('details'))
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
            await self.close()

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
