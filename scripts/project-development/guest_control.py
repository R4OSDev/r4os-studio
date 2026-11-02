"""One sequenced private SSH-stdio controller, never a general guest shell."""
import asyncio
import base64
import json
import re
from contracts import DevelopmentFault, UnconfirmedGuestEffect, encode

class GuestControl:
    def __init__(self, ssh, deployment, execution_id, work=None):
        self.ssh, self.deployment, self.id = ssh, deployment, execution_id
        self.sequence = 0; self.process = None; self.lock = asyncio.Lock(); self.error_task = None
        self.work = work; self.pending_operation = 'open'
        self.stderr = bytearray(); self.stderr_limited = False; self.initial_response = None
        self.startup_rejected = None; self.loss = None

    def module_matches(self, value):
        path = value.get('modulePath')
        if not isinstance(path, str): return False
        normalize = lambda p: re.sub(r'\\+', lambda _: chr(92), p.replace('/', chr(92)).rstrip(chr(0))).upper()
        return normalize(path) == normalize(self.deployment['guestDirectory'] + chr(92) + 'STHELP.R4X')

    def diagnostics(self, final=False, terminated=False):
        if self.work is None: return
        from layout import save
        save(self.work / 'guest-control-diagnostics.json', {'schema': 1, 'executionId': self.id,
            'sequence': self.sequence, 'operation': self.pending_operation, 'final': final,
            'initialResponseBase64': base64.b64encode(self.initial_response).decode() if self.initial_response is not None else None,
            'stderrBase64': base64.b64encode(self.stderr).decode(), 'stderrTruncated': self.stderr_limited,
            'sshExitCode': self.process.returncode if self.process else None,
            'sshClientTerminatedByHost': terminated})

    def lost(self, phase):
        if self.work is None: return
        from layout import save
        from jobs import now
        self.loss = {'schema': 1, 'executionId': self.id,
            'sequence': self.sequence, 'operation': self.pending_operation, 'phase': phase,
            'channel': 'ssh-stdio', 'observedAt': now(),
            'localSshProcessId': self.process.pid if self.process else None,
            'sshExitCode': self.process.returncode if self.process else None}
        save(self.work / 'guest-control-loss.json', self.loss)
        self.diagnostics()

    async def open(self):
        command = self.deployment['guestDirectory'] + chr(92) + 'STHELP.R4X ' + self.id + ' serve'
        self.process = await asyncio.create_subprocess_exec(*self.ssh.argv(), self.ssh.record['username'] + '@127.0.0.1', command,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.ssh.environment(), limit=65537, start_new_session=True)
        self.ssh.processes.add(self.process)
        async def drain():
            while data := await self.process.stderr.read(4096):
                available = 65536 - len(self.stderr)
                self.stderr.extend(data[:available])
                if len(data) > available:
                    self.stderr_limited = True
                    if self.process.returncode is None: self.process.kill()
                    return
        self.error_task = asyncio.create_task(drain())
        value = await self.read()
        if value['result'].get('controlVersion') != 2 or value['result'].get('watchdogVersion') != 1 or not self.module_matches(value['result']):
            raise UnconfirmedGuestEffect('The guest controller identity does not match this deployment. Original helper effects remain unconfirmed.')
        return value

    async def read(self):
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), 8)
            if self.sequence == 0:
                self.initial_response = line[:65536]
                self.diagnostics()
            if not line or len(line) > 65536: raise ValueError()
            value = json.loads(line)
            if (not isinstance(value, dict) or value.get('instance') != self.id
                or type(value.get('sequence')) is not int or value['sequence'] != self.sequence
                or type(value.get('version')) is not int or value['version'] != 1
                or type(value.get('success')) is not bool or not isinstance(value.get('result'), dict)): raise ValueError()
            result = value['result']
            if not value['success']:
                if self.sequence == 0:
                    from layout import save
                    if self.work is not None: save(self.work / 'controller-startup-response.json', value)
                    phase = result.get('phase')
                    valid = (self.deployment.get('helperCapabilities', {}).get('watchdogLaunchVersion') == 2
                        and type(result.get('startupFailureVersion')) is int and result['startupFailureVersion'] == 1
                        and result.get('applicationStarted') is False and self.module_matches(result)
                        and type(result.get('rawCode')) is int)
                    if (valid and result.get('startupCleanupConfirmed') is True
                        and phase in ('relay_identity', 'watchdog_capability', 'watchdog_intent', 'watchdog_spawn')):
                        self.startup_rejected = value
                        raise DevelopmentFault(f'Guest controller startup failed at {phase} (native code {result["rawCode"]}). No application was started.')
                    raise UnconfirmedGuestEffect('Guest controller startup did not confirm cleanup. Inspect the original startup response; no application start was sent.')
                raise DevelopmentFault(result.get('error', 'The guest request failed.'))
            return value
        except (asyncio.TimeoutError, OSError, ValueError):
            self.lost('read')
            raise UnconfirmedGuestEffect('The guest control receipt was lost. No start or input was replayed.') from None

    async def call(self, operation, **input):
        async with self.lock:
            self.pending_operation = operation
            self.sequence += 1
            message = encode({'version': 1, 'instance': self.id, 'sequence': self.sequence, 'operation': operation, **input}) + '\n'
            if len(message.encode()) > 4096: raise DevelopmentFault('Guest request exceeds the frame limit.', 400)
            try:
                self.process.stdin.write(message.encode()); await self.process.stdin.drain()
            except (OSError, ConnectionError):
                self.lost('write')
                raise UnconfirmedGuestEffect('The guest control channel closed without a receipt.') from None
            result = (await self.read())['result']
            if 'state' in result: result['controllerSequence'] = self.sequence
            return result

    async def close(self):
        terminated = False
        if self.process:
            if self.process.returncode is None:
                try: await asyncio.wait_for(self.process.wait(), .5)
                except asyncio.TimeoutError:
                    if self.process.returncode is None:
                        terminated = True; self.process.kill()
                    await self.process.wait()
            self.ssh.processes.discard(self.process)
        if self.error_task:
            if not self.error_task.done():
                try: await asyncio.wait_for(asyncio.shield(self.error_task), .5)
                except asyncio.TimeoutError: pass
            self.error_task.cancel(); await asyncio.gather(self.error_task, return_exceptions=True)
        self.diagnostics(final=True, terminated=terminated)
