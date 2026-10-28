"""Private line-framed app-server RPC, including asynchronous server requests."""
import asyncio
import json


class RPCRejected(RuntimeError):
    """A native error reply, distinct from a lost connection or response."""
    def __init__(self, code):
        super().__init__('The native agent rejected this request.')
        self.code = code


class CodexRPC:
    def __init__(self, args, notification, server_request):
        self.args = args; self.notification = notification; self.server_request = server_request
        self.pending = {}; self.sequence = 0; self.child = None; self.reader = None
        self.requests = set(); self.closing = False; self.inbound_limit=1048576

    async def start(self):
        self.child = await asyncio.create_subprocess_exec(*self.args, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=self.inbound_limit, start_new_session=True)
        self.reader = asyncio.create_task(self.receive())
        await self.request('initialize', {'clientInfo': {'name': 'r4os_studio_agent', 'title': 'R4OS Studio', 'version': self.version},
                                        'capabilities': {'experimentalApi': True}})
        await self.send({'method': 'initialized'})

    async def send(self, value):
        if not self.child or self.child.returncode is not None: raise RuntimeError('The agent process stopped.')
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
        if len(raw) > 1048576: raise RuntimeError('Agent message exceeds the protocol limit.')
        self.child.stdin.write(raw); await self.child.stdin.drain()

    async def request(self, method, params, timeout=45):
        self.sequence += 1; ident = self.sequence
        future = asyncio.get_running_loop().create_future(); self.pending[ident] = future
        try:
            await self.send({'id': ident, 'method': method, 'params': params})
            return await asyncio.wait_for(future, timeout)
        finally: self.pending.pop(ident, None)

    async def answer(self, frame):
        try:
            if frame['method'] == 'item/tool/call':
                result = await self.server_request(frame['params'])
                await self.send({'id': frame['id'], 'result': result})
            else:
                await self.send({'id': frame['id'], 'error': {'code': -32601, 'message': 'Unavailable in this Studio session.'}})
        except asyncio.CancelledError: pass
        except Exception:
            if not self.closing:
                try: await self.send({'id': frame['id'], 'error': {'code': -32603, 'message': 'The Studio tool could not complete.'}})
                except Exception: pass

    async def receive(self):
        try:
            while raw := await self.child.stdout.readline():
                if len(raw) > self.inbound_limit: raise RuntimeError('Agent frame exceeds the protocol limit.')
                frame = json.loads(raw)
                if not isinstance(frame, dict): continue
                if 'method' in frame and 'id' in frame:
                    task = asyncio.create_task(self.answer(frame)); self.requests.add(task)
                    task.add_done_callback(self.requests.discard)
                elif 'method' in frame:
                    await self.notification(frame['method'], frame.get('params') or {})
                elif 'id' in frame:
                    future = self.pending.get(frame['id'])
                    if future and not future.done():
                        if 'error' in frame: future.set_exception(RPCRejected(frame['error'].get('code')))
                        else: future.set_result(frame.get('result'))
        except asyncio.CancelledError: pass
        except Exception: pass
        finally:
            for future in self.pending.values():
                if not future.done(): future.set_exception(RuntimeError('The agent connection closed.'))
            if not self.closing: await self.notification('studio/processExited', {})

    async def close(self):
        self.closing = True
        for task in list(self.requests): task.cancel()
        if self.requests: await asyncio.gather(*self.requests, return_exceptions=True)
        if self.child and self.child.returncode is None:
            self.child.terminate()
            try: await asyncio.wait_for(self.child.wait(), 5)
            except asyncio.TimeoutError: self.child.kill(); await self.child.wait()
        if self.reader:
            self.reader.cancel(); await asyncio.gather(self.reader, return_exceptions=True)
