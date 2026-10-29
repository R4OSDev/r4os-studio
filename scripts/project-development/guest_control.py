"""One sequenced private SSH-stdio controller, never a general guest shell."""
import asyncio
import json
import re
from contracts import DevelopmentFault, UnconfirmedGuestEffect, encode

class GuestControl:
    def __init__(self, ssh, deployment, execution_id):
        self.ssh, self.deployment, self.id = ssh, deployment, execution_id
        self.sequence = 0; self.process = None; self.lock = asyncio.Lock(); self.error_task = None

    async def open(self):
        command = self.deployment['guestDirectory'] + chr(92) + 'STHELP.R4X ' + self.id + ' serve'
        self.process = await asyncio.create_subprocess_exec(*self.ssh.argv(), self.ssh.record['username'] + '@127.0.0.1', command,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.ssh.environment(), limit=65537, start_new_session=True)
        self.ssh.processes.add(self.process)
        async def drain():
            count = 0
            while data := await self.process.stderr.read(4096):
                count += len(data)
                if count > 65536: self.process.kill(); return
        self.error_task = asyncio.create_task(drain())
        value = await self.read()
        expected = self.deployment['guestDirectory'] + chr(92) + 'STHELP.R4X'
        normalize = lambda p: re.sub(r'\\+', lambda _: chr(92), p.replace('/', chr(92)).rstrip(chr(0))).upper()
        if value['result'].get('controlVersion') != 2 or value['result'].get('watchdogVersion') != 1 or normalize(value['result'].get('modulePath', '')) != normalize(expected):
            raise DevelopmentFault('The guest controller identity does not match this deployment.')
        return value

    async def read(self):
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), 8)
            if not line or len(line) > 65536: raise ValueError()
            value = json.loads(line)
            if value.get('instance') != self.id or value.get('sequence') != self.sequence or value.get('version') != 1: raise ValueError()
            if not value.get('success'): raise DevelopmentFault(value.get('result', {}).get('error', 'The guest request failed.'))
            return value
        except (asyncio.TimeoutError, OSError, ValueError):
            raise UnconfirmedGuestEffect('The guest control receipt was lost. No start or input was replayed.') from None

    async def call(self, operation, **input):
        async with self.lock:
            self.sequence += 1
            message = encode({'version': 1, 'instance': self.id, 'sequence': self.sequence, 'operation': operation, **input}) + '\n'
            if len(message.encode()) > 4096: raise DevelopmentFault('Guest request exceeds the frame limit.', 400)
            try:
                self.process.stdin.write(message.encode()); await self.process.stdin.drain()
            except (OSError, ConnectionError): raise UnconfirmedGuestEffect('The guest control channel closed without a receipt.') from None
            result = (await self.read())['result']
            if 'state' in result: result['controllerSequence'] = self.sequence
            return result

    async def close(self):
        if self.process:
            if self.process.returncode is None:
                self.process.kill(); await self.process.wait()
            self.ssh.processes.discard(self.process)
        if self.error_task:
            self.error_task.cancel(); await asyncio.gather(self.error_task, return_exceptions=True)
