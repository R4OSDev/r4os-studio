"""Private stdio MCP transport. Callers supply only verified managed launchers."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import uuid

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
MAX_FRAME = 32 * 1024 * 1024
MAX_CATALOG = 32 * 1024 * 1024
MAX_ARGUMENTS = 1024 * 1024


class McpFault(Exception):
    def __init__(self, message, request_id=None, state=None):
        super().__init__(message)
        self.request_id, self.state = request_id, state


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def directory(path):
    path = Path(path).absolute()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
        raise McpFault('The private MCP state directory is linked or unavailable.')
    return path


def atomic(path, raw):
    temporary = path.with_name('.write-' + str(uuid.uuid4()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temporary.exists(): temporary.unlink()


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON member.')
            result[key] = value
        return result
    def invalid(_): raise ValueError('Non-JSON numeric value.')
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs, parse_constant=invalid)


def birth(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


class Client:
    def __init__(self, state, binding, progress=None):
        self.directory = directory(state)
        self.calls = directory(self.directory / 'Calls')
        self.binding = binding
        self.progress = progress
        self.process = None
        self.pending = {}
        self.receipts = {}
        self.write_lock = asyncio.Lock()
        self.tasks = []
        self.tools = {}
        self.capabilities = {}
        self.catalog_changed = False
        self.owner = dict(schema=1, binding=binding, processEndConfirmed=False)
        self.stopping = False

    def own(self, **changes):
        self.owner.update(changes)
        atomic(self.directory / 'process.json', encoded(self.owner))

    def record(self, ident, **changes):
        value = self.receipts[ident]
        value.update(changes)
        atomic(self.calls / (ident + '.json'), encoded(value))
        return value

    async def start(self, command, cwd=None, env=None, timeout=30):
        if self.process is not None or (self.directory / 'process.json').exists():
            raise McpFault('An original MCP process already owns this directory. Observe it instead of starting another.')
        if (not isinstance(command, list) or not command or not all(isinstance(s, str) and '\0' not in s for s in command)
                or not Path(command[0]).is_absolute() or env is None):
            raise McpFault('A managed absolute start vector and explicit private environment are required.')
        self.own(phase='starting', commandHash=hashlib.sha256(encoded(command)).hexdigest())
        try:
            self.process = await asyncio.create_subprocess_exec(*command, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=MAX_FRAME + 1, start_new_session=True)
        except OSError:
            self.own(phase='start_failed', processEndConfirmed=True, neverStarted=True)
            raise McpFault('The managed MCP executable could not start; no provider operation was submitted.') from None
        self.own(phase='initializing', pid=self.process.pid, birth=birth(self.process.pid), workerPid=os.getpid(),
                 workerBirth=birth(os.getpid()), release=str(Path(__file__).resolve().parents[2]))
        self.tasks = [asyncio.create_task(self.read()), asyncio.create_task(self.stderr()), asyncio.create_task(self.watch())]
        try:
            result = await self.request('initialize', dict(protocolVersion=PROTOCOLS[0], capabilities={},
                clientInfo=dict(name='r4os-studio-skill-client', version='1')), timeout=timeout)
            if (not isinstance(result, dict) or result.get('protocolVersion') not in PROTOCOLS
                    or not isinstance(result.get('capabilities'), dict) or not isinstance(result.get('serverInfo'), dict)):
                raise McpFault('The MCP server negotiated an unsupported protocol or malformed capabilities.')
            self.capabilities = result['capabilities']
            self.own(phase='ready', initialize=result)
            await self.notify('notifications/initialized', {})
            return result
        except BaseException:
            await self.close()
            raise

    async def send(self, value):
        raw = encoded(value) + b'\n'
        if len(raw) > MAX_FRAME: raise McpFault('The MCP request exceeds its explicit frame limit.')
        async with self.write_lock:
            if self.process is None or self.process.returncode is not None or self.process.stdin.is_closing():
                raise McpFault('The original MCP transport is closed; no replacement process was started.')
            self.process.stdin.write(raw)
            await self.process.stdin.drain()

    async def notify(self, method, params):
        await self.send(dict(jsonrpc='2.0', method=method, params=params))

    async def request(self, method, params, timeout=120, request_id=None):
        ident = request_id or str(uuid.uuid4())
        if not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident):
            raise McpFault('Invalid original MCP request identity.')
        arguments = encoded(params)
        if len(arguments) > MAX_ARGUMENTS or not isinstance(params, dict):
            raise McpFault('MCP arguments must be a JSON object within 1 MiB.')
        fingerprint = hashlib.sha256(encoded(dict(method=method, params=params))).hexdigest()
        previous = self.calls / (ident + '.json')
        if previous.exists():
            value = strict(previous.read_bytes())
            if value['fingerprint'] != fingerprint: raise McpFault('This MCP request identity belongs to different arguments.', ident)
            if value['phase'] in ('complete', 'late_result'):
                response = strict((self.calls / (ident + '.response.json')).read_bytes())
                return self.result(response, ident)
            raise McpFault('Observe this original MCP request; its effect must not be submitted again.', ident, value)
        if len(self.pending) >= 8: raise McpFault('This private MCP process already has eight outstanding original requests.')
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        self.receipts[ident] = dict(schema=1, requestId=ident, method=method, params=params, fingerprint=fingerprint,
                                    phase='prepared', providerEndConfirmed=False, clientInterrupted=False)
        self.record(ident)
        try:
            self.record(ident, phase='send_intent')
            await self.send(dict(jsonrpc='2.0', id=ident, method=method, params=params))
            if not future.done(): self.record(ident, phase='sent')
            response = await asyncio.wait_for(asyncio.shield(future), timeout)
            return self.result(response, ident)
        except (TimeoutError, asyncio.CancelledError) as error:
            if isinstance(error, TimeoutError) and future.done() and not future.cancelled():
                return self.result(future.result(), ident)
            if not future.done():
                self.record(ident, phase='cancel_requested', clientInterrupted=True, clientTimeout=isinstance(error, TimeoutError))
                if method != 'initialize':
                    try: await self.notify('notifications/cancelled', dict(requestId=ident, reason='Studio client interrupted the original wait.'))
                    except (OSError, McpFault): pass
                # Retain this future for its original late response; do not cancel/retry the native operation.
                future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            if isinstance(error, asyncio.CancelledError): raise
            raise McpFault('The MCP wait expired. The original provider operation is not confirmed ended.', ident, self.receipts[ident]) from None
        except (OSError, McpFault):
            if not future.done():
                self.record(ident, phase='unknown', transportClosed=True)
                future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            raise

    def result(self, response, ident):
        if 'error' in response:
            raise McpFault('The original MCP request returned a protocol error.', ident, response['error'])
        return response['result']

    async def read(self):
        reason = 'The MCP stream ended before an original response was received.'
        try:
            while raw := await self.process.stdout.readline():
                if len(raw) > MAX_FRAME or not raw.endswith(b'\n'): raise ValueError('Incomplete or oversized MCP frame.')
                value = strict(raw)
                if not isinstance(value, dict) or value.get('jsonrpc') != '2.0': raise ValueError('Invalid MCP envelope.')
                if 'method' in value:
                    method = value['method']
                    if not isinstance(method, str): raise ValueError('Invalid MCP method.')
                    if 'id' in value:
                        if method == 'ping': await self.send(dict(jsonrpc='2.0', id=value['id'], result={}))
                        else: await self.send(dict(jsonrpc='2.0', id=value['id'], error=dict(code=-32601, message='This client does not offer that capability.')))
                    elif method == 'notifications/tools/list_changed': self.catalog_changed = True
                    elif method == 'notifications/progress':
                        params = value.get('params', {})
                        token = params.get('progressToken') if isinstance(params, dict) else None
                        if token in self.receipts: self.record(token, progress=params)
                        if self.progress is not None: await self.progress(value)
                    else:
                        # Last native notification is diagnostic only; it never becomes a tool result.
                        atomic(self.directory / 'last-notification.json', encoded(value))
                    continue
                ident = value.get('id')
                if not isinstance(ident, str) or ident not in self.pending:
                    atomic(self.directory / 'orphan-response.json', raw)
                    continue
                if ('error' in value) == ('result' in value): raise ValueError('Ambiguous MCP response.')
                future = self.pending.pop(ident)
                atomic(self.calls / (ident + '.response.json'), raw)
                phase = 'late_result' if self.receipts[ident].get('clientInterrupted') else 'complete'
                self.record(ident, phase=phase, providerEndConfirmed=True,
                            responseHash=hashlib.sha256(raw).hexdigest(), responseBytes=len(raw))
                if not future.done(): future.set_result(value)
        except (OSError, ValueError, UnicodeError) as error:
            reason = 'The MCP stream failed its framing, UTF-8 or JSON contract: ' + type(error).__name__
        finally:
            self.own(transportClosed=True, transportReason=reason)
            for ident, future in list(self.pending.items()):
                self.record(ident, phase='unknown', transportClosed=True)
                if not future.done(): future.set_exception(McpFault(reason, ident, self.receipts[ident]))
            self.pending.clear()

    async def stderr(self):
        total = 0; kept = 0
        fd = os.open(self.directory / 'stderr.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            while data := await self.process.stderr.read(65536):
                total += len(data)
                part = data[:max(0, 8 * 1024 * 1024 - kept)]
                stream.write(part); kept += len(part)
        self.own(stderrBytes=total, stderrKeptBytes=kept, stderrTruncated=kept != total)

    async def watch(self):
        code = await self.process.wait()
        self.own(phase='ended', exit=code, processEndConfirmed=True)

    async def listing(self, method, key):
        result = []; cursor = None; seen = set(); size = 0
        for _ in range(1024):
            value = await self.request(method, {} if cursor is None else dict(cursor=cursor))
            if not isinstance(value, dict) or not isinstance(value.get(key), list): raise McpFault('The MCP list result is malformed.')
            size += len(encoded(value))
            if size > MAX_CATALOG or len(result) + len(value[key]) > 10000:
                raise McpFault('The complete MCP catalogue exceeds its explicit limit; no partial catalogue was accepted.')
            result.extend(value[key]); cursor = value.get('nextCursor')
            if cursor is None: return result
            if not isinstance(cursor, str) or cursor in seen: raise McpFault('The MCP list cursor repeats or is invalid.')
            seen.add(cursor)
        raise McpFault('The MCP list exceeded 1024 pages; no partial catalogue was accepted.')

    async def discover(self):
        if 'tools' not in self.capabilities: raise McpFault('This MCP server does not advertise tools.')
        tools = await self.listing('tools/list', 'tools')
        result = {}
        for tool in tools:
            if (not isinstance(tool, dict) or not isinstance(tool.get('name'), str) or not 1 <= len(tool['name']) <= 256
                    or not isinstance(tool.get('inputSchema'), dict) or tool['name'] in result):
                raise McpFault('The MCP catalogue has malformed schemas or duplicate tool names.')
            result[tool['name']] = tool
        self.tools = result; self.catalog_changed = False
        atomic(self.directory / 'tools.json', encoded(tools))
        self.own(catalogHash=hashlib.sha256(encoded(tools)).hexdigest(), tools=len(tools))
        return tools

    async def call(self, name, arguments, request_id=None, timeout=120):
        if self.catalog_changed: raise McpFault('The server catalogue changed. Accept a new run before using different tool contracts.')
        if name not in self.tools: raise McpFault('This method is absent from the confirmed complete MCP catalogue.')
        if not isinstance(arguments, dict): raise McpFault('MCP tool arguments must retain their JSON object shape.')
        ident = request_id or str(uuid.uuid4())
        return await self.request('tools/call', dict(name=name, arguments=arguments, _meta=dict(progressToken=ident)), timeout, ident)

    def observe(self, ident):
        if not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise McpFault('Invalid MCP request identity.')
        return strict((self.calls / (ident + '.json')).read_bytes())

    async def close(self, grace=10):
        if self.process is None: return dict(processEndConfirmed=True, neverStarted=True)
        self.stopping = True
        if self.process.returncode is None:
            self.process.stdin.close()
            try: await asyncio.wait_for(asyncio.shield(self.process.wait()), grace)
            except TimeoutError:
                if self.process.returncode is None and birth(self.process.pid) == self.owner['birth']:
                    os.killpg(self.process.pid, signal.SIGTERM)
                try: await asyncio.wait_for(asyncio.shield(self.process.wait()), 5)
                except TimeoutError:
                    if self.process.returncode is None and birth(self.process.pid) == self.owner['birth']:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    await self.process.wait()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        return dict(processEndConfirmed=self.process.returncode is not None, exit=self.process.returncode,
                    unresolved=[ident for ident, value in self.receipts.items() if value['phase'] not in ('complete', 'late_result')])
