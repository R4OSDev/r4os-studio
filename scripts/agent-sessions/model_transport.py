"""Private direct model transport; connectors never run tools or continuations."""
import asyncio
import base64
import codecs
import json
from pathlib import Path

from api_endpoint import resolve_binding
from store import ProjectFault


class ModelFault(ProjectFault):
    def __init__(self, code='model_protocol_error', http_status=None):
        messages = {401: 'The provider credential was rejected.', 402: 'The API account needs credits or billing attention.',
                    403: 'The account cannot access the selected model.', 404: 'The selected model or API route was not found.',
                    429: 'The model service is rate or usage limited.'}
        message = messages.get(http_status, 'The model response could not be confirmed. It was not repeated.')
        super().__init__(message, 503)
        self.code = code
        self.http_status = http_status


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

    async def response(self, messages, instructions, tools, effort='', on_text=None, on_reasoning=None):
        if self.binding['protocol'] == 'responses':
            from model_responses import request, Responses
            body = request(self.binding, messages, instructions, tools, effort)
            parser = Responses(self.binding, tools)
        elif self.binding['protocol'] == 'chat-completions':
            from model_chat import request, Chat
            body, headers = request(self.binding, messages, instructions, tools, effort, self.chat_policy, self.client)
            self.headers = {**self.headers, **headers}
            parser = Chat(self.binding, tools)
        else:
            raise ModelFault('model_protocol_unavailable')
        await self.send(body, parser, on_text, on_reasoning)
        return parser.result()

    async def send(self, body, parser, on_text=None, on_reasoning=None):
        if self.child is not None:
            raise ModelFault('model_request_busy')
        raw_body = dumps(body)
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
            self.child.stdin.write(bootstrap)
            await self.child.stdin.drain()
            self.child.stdin.close()
            while raw := await self.child.stdout.readline():
                frame = loads(raw)
                if not isinstance(frame, dict): raise ModelFault()
                if frame.get('type') == 'error':
                    raise ModelFault(frame.get('code', 'model_transport_error'), frame.get('httpStatus'))
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
        self.child = None
