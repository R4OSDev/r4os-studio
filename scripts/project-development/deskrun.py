"""DESKRUN 0.1.1: one submission, lossless receipts, status-only reconciliation.

DESKRUN terminates a launch/wait request, never the application lifecycle. Its
u64 counters are parsed as Python integers and exported only as decimal strings.
"""
import asyncio
import base64
import json
import re
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from jobs import now
from layout import save

ERRORS = ('ok', 'transport', 'syntax', 'resolution', 'no_desktop', 'queue_full',
          'window_full', 'loader', 'attachment', 'timeout', 'desktop_lost',
          'process_ended', 'invalid', 'unknown', 'stale_service')
PHASES = ('request', 'accepted', 'starting', 'process', 'window', 'content')
U64 = 18446744073709551615
# R4OS SSHD wraps exec in `/NOAUTOEXEC /C ` before spawning Terminal.
# Its 128-byte argument buffer includes NUL (SSHD dba200989d63,
# buildExecTerminalArgs). Budget the entire command, including DESKRUN.
SSH_EXEC_PREFIX = '/NOAUTOEXEC /C '
SSH_EXEC_BYTES = 127 - len(SSH_EXEC_PREFIX.encode())
DEFAULT_WAIT_MS = 5000


class NotSubmitted(DevelopmentFault):
    launch_not_submitted = True


def request_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,20}(?::[0-9]{1,20}){3}', value):
        raise ValueError('Invalid DESKRUN request identity.')
    if any(not 0 < int(part) <= limit for part, limit in zip(value.split(':'), (4294967295, U64, 4294967295, U64))):
        raise ValueError('Invalid DESKRUN request identity.')
    return value  # The complete original spelling is the durable query key.


def receipt(output):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate DESKRUN field.')
            result[key] = value
        return result
    lines = output.decode('utf-8', errors='strict').splitlines()
    line = next((line for line in reversed(lines) if line.strip()), '')
    def invalid_constant(_): raise ValueError('Invalid JSON constant.')
    value = json.loads(line, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(value, dict): raise ValueError('Invalid DESKRUN receipt.')
    code = value.get('errorlevel')
    if type(code) is not int or not 0 <= code < len(ERRORS): raise ValueError('Invalid DESKRUN errorlevel.')
    if value.get('phase') == 'before_submit':
        if set(value) != {'phase', 'errorlevel', 'error'} or not isinstance(value['error'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value['error']):
            raise ValueError('Invalid pre-submission diagnostic.')
        return value
    fields = {'request', 'phase', 'error', 'errorlevel', 'process_id', 'process_generation', 'window', 'content', 'raw', 'terminal'}
    if set(value) != fields or value['phase'] not in PHASES or value['error'] != ERRORS[code] or type(value['terminal']) is not bool:
        raise ValueError('Unsupported DESKRUN receipt.')
    request_key(value['request'])
    for name, maximum in (('process_id', 4294967295), ('process_generation', U64), ('window', 2147483647), ('content', U64)):
        if type(value[name]) is not int or not 0 <= value[name] <= maximum: raise ValueError('Invalid DESKRUN counter.')
    if type(value['raw']) is not int or not -2147483648 <= value['raw'] <= 2147483647: raise ValueError('Invalid DESKRUN diagnostic.')
    if bool(value['process_id']) != bool(value['process_generation']): raise ValueError('Incomplete DESKRUN process identity.')
    phase = PHASES.index(value['phase'])
    if (phase >= 3 and not value['process_id']) or (value['window'] and not value['process_id']) or (phase >= 4 and not value['window']) or (value['content'] and not value['window']) or (phase == 5 and not value['content']):
        raise ValueError('Inconsistent DESKRUN progress.')
    return {**value, 'process_generation': str(value['process_generation']), 'content': str(value['content'])}


def command_text(deployment, arguments, wait_ms):
    path = deployment['guestDirectory'] + chr(92) + 'APP.R4X'
    # This is a fixed verified package path, never a caller-selected shell path.
    if not re.fullmatch(r'[A-Z]:\\Build\\P[A-F0-9]{7}\\D[A-F0-9]{7}\\APP\.R4X', path, re.IGNORECASE):
        raise NotSubmitted('The native Desktop target is not a verified Exchange Build application.')
    if any(ord(c) < 32 or ord(c) == 127 for c in arguments) or any(c in arguments for c in '&|<>;'):
        raise NotSubmitted('Desktop arguments cannot contain shell control characters.', 400)
    # Use DESKRUN's native five-second default without spending argument bytes
    # on an optional flag. Short execution deadlines still get an explicit wait.
    wait = '' if wait_ms == DEFAULT_WAIT_MS else f' /WAIT:{wait_ms}'
    text = f'DESKRUN /JSON{wait} /WAITFRAME "{path}"' + (' ' + arguments if arguments else '')
    return text


def launch_budget(deployment, arguments, wait_ms):
    text = command_text(deployment, arguments, wait_ms)
    fixed = len(command_text(deployment, '', wait_ms).encode())
    try: used = len(text.encode()); argument_bytes = len(arguments.encode())
    except UnicodeError: raise NotSubmitted('Desktop arguments must contain valid UTF-8 text. No application was started.',400) from None
    capacity = SSH_EXEC_BYTES - fixed - 1
    return {'available': True, 'commandBytes': used, 'limitBytes': SSH_EXEC_BYTES,
        'wrapperBytes': len(SSH_EXEC_PREFIX.encode()), 'fixedBytes': fixed, 'argumentBytes': argument_bytes,
        'argumentCapacityBytes': capacity, 'remainingArgumentBytes': capacity - argument_bytes,
        'remainingCommandBytes': SSH_EXEC_BYTES - used, 'overByBytes': max(0,used - SSH_EXEC_BYTES),
        'waitMilliseconds': wait_ms, 'withinLimit': used <= SSH_EXEC_BYTES}


def command(deployment, arguments, wait_ms):
    value = launch_budget(deployment, arguments, wait_ms)
    if not value['withinLimit']:
        raise NotSubmitted(f"Desktop launch requires {value['commandBytes']} UTF-8 command bytes; R4OS SSHD allows {SSH_EXEC_BYTES} after its Terminal wrapper. Shorten the application arguments. No application was started.",
            400, reason_code='desktop_arguments_too_long')
    return command_text(deployment, arguments, wait_ms)


async def exchange(ssh, text, timeout):
    """Keep partial stdout even when SSH loses its exit status or deadline."""
    try:
        process = await asyncio.create_subprocess_exec(*ssh.argv(), ssh.record['username'] + '@127.0.0.1', text,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=ssh.environment(), start_new_session=True)
    except OSError: raise NotSubmitted('The local DESKRUN SSH client could not be started.') from None
    ssh.processes.add(process); out = bytearray(); error = bytearray(); incomplete = False
    async def read(stream, target):
        while data := await stream.read(4096):
            if len(target) + len(data) > 65536: raise ValueError('DESKRUN output exceeds its limit.')
            target.extend(data)
    readers = [asyncio.create_task(read(process.stdout, out)), asyncio.create_task(read(process.stderr, error))]
    try:
        await asyncio.wait_for(asyncio.gather(*readers, process.wait()), timeout)
    except (asyncio.TimeoutError, ValueError, OSError): incomplete = True
    finally:
        if process.returncode is None:
            process.kill(); await process.wait()
        for task in readers: task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        ssh.processes.discard(process)
    return {'stdout': bytes(out), 'stderr': bytes(error), 'sshExitCode': process.returncode,
            'transportUncertain': incomplete or process.returncode == 255 or process.returncode < 0}


async def capability(ssh):
    # Read-only syntax/receipt discovery. Never start an app as a capability test.
    response = await exchange(ssh, 'DESKRUN /JSON /STATUS:1:1:1:1', 8)
    try: value = receipt(response['stdout'])
    except (ValueError, UnicodeError):
        raise DevelopmentFault('The assigned guest does not expose the DESKRUN JSON launch/status contract. No application was started.', reason_code='deskrun_unavailable') from None
    if response['transportUncertain']:
        raise DevelopmentFault('DESKRUN capability discovery lost its SSH transport. No application was started.')
    if value['phase'] == 'before_submit':
        raise DevelopmentFault('DESKRUN is unavailable: ' + value['error'] + '. No application was started.', reason_code='deskrun_unavailable')
    return {'interface': 'DESKRUN', 'contract': '0.1.1', 'checkedAt': now()}


def frame_ready(job, state):
    value = job.get('desktopLaunch') or {}
    return (value.get('phase') == 'content' and value.get('errorlevel') in (0, 9) and int(value.get('content', '0')) > 0
        and value.get('process_id') == state.get('instanceId') and value.get('process_generation') == state.get('generation')
        and value.get('window', 0) > 0 and value['window'] - 1 == state.get('windowId')
        and state.get('state') == 'running' and bool(state.get('windowVisible')) and not state.get('closeConfirmed'))

def diagnostic_window(job, state):
    """Own visible/focused window proof, explicitly without a content-ready claim."""
    value = job.get('desktopLaunch') or {}; process = job.get('process') or {}
    try:
        request_key(value['request'])
        return (job.get('kind') == 'execution' and job.get('state') == 'running'
            and (job.get('readiness') or {}).get('reasonCode') == 'desktop_content_unconfirmed'
            and value.get('phase') == 'window' and value.get('errorlevel') == 9 and value.get('content') == '0'
            and type(value.get('process_id')) is int and value['process_id'] > 0
            and value['process_id'] == process.get('instanceId') == state.get('instanceId')
            and value.get('process_generation') == process.get('generation') == state.get('generation')
            and type(value.get('window')) is int and value['window'] > 0
            and value['window'] - 1 == process.get('windowId') == state.get('windowId')
            and state.get('state') == 'running' and not state.get('closeConfirmed') and not state.get('stopReason')
            and state.get('windowVisible') is True and state.get('windowFocused') is True
            and all(type(state.get(k)) is int and 0 < state[k] <= limit for k, limit in (('windowWidth',1280),('windowHeight',1024)))
            and type(state.get('guiRevision')) is int and state['guiRevision'] > 0)
    except (KeyError, TypeError, ValueError): return False


class DesktopLaunch:
    def __init__(self, execution, ssh, deployment, lease):
        self.owner, self.ssh, self.deployment, self.lease = execution, ssh, deployment, lease
        self.store, self.job = execution.store, execution.job
        self.key = None; self.value = None; self.index = 0; self.process = None
        self.deadline = None; self.next_status = 0; self.status_expired = False
        self.force_status = False; self.heartbeat_done = asyncio.Event()

    def guard(self, stopping=False):
        from vm_worker import guard
        guard(self.store, self.job, self.lease, allow_stopping=stopping)

    async def query(self, text, timeout, starting=False):
        self.guard(stopping=not starting)
        self.index += 1
        root = self.owner.work / ('deskrun-' + str(self.index))
        save(root.with_suffix('.intent.json'), {'operation': 'start' if starting else 'status', 'request': self.key, 'command': text, 'createdAt': now()})
        try: response = await exchange(self.ssh, text, timeout)
        except NotSubmitted:
            if starting: raise
            return None
        save(root.with_suffix('.transport.json'), {k: base64.b64encode(v).decode() if isinstance(v, bytes) else v for k, v in response.items()})
        try: value = receipt(response['stdout'])
        except (ValueError, UnicodeError):
            if starting:
                raise UnconfirmedGuestEffect('Launch outcome unknown: SSH returned no valid DESKRUN request identity. No launch was repeated.') from None
            return None
        save(root.with_suffix('.receipt.json'), value)
        if value['phase'] == 'before_submit':
            if starting: raise NotSubmitted('DESKRUN rejected the launch before submission: ' + value['error'] + '.')
            if self.value:
                self.store.update(self.job['id'], desktopLaunch={**self.value, 'statusError': value['error'], 'statusErrorlevel': value['errorlevel'], 'checkedAt': now()})
            return None  # A failed STATUS query says nothing about the launch.
        if self.key is not None and value['request'] != self.key:
            raise UnconfirmedGuestEffect('DESKRUN returned a different request identity. No launch was repeated.')
        if self.key is None: self.key = value['request']
        if starting: self.force_status = response['transportUncertain']
        else: self.force_status = False
        if self.process and value['process_id'] and (value['process_id'], value['process_generation']) != self.process:
            raise UnconfirmedGuestEffect('The DESKRUN process generation changed. No launch was repeated.')
        # Missing/stale status is absence of evidence, never evidence of no start.
        if not starting and value['errorlevel'] in (13, 14):
            self.status_expired = True
            self.store.update(self.job['id'], desktopLaunch={**(self.value or value), 'statusError': value['error'], 'statusErrorlevel': value['errorlevel'], 'checkedAt': now()})
            return None
        if self.value and PHASES.index(value['phase']) < PHASES.index(self.value['phase']):
            return None  # Retain the last confirmed progress; keep raw history.
        self.value = {**value, 'adapter': 'DESKRUN', 'contract': '0.1.1', 'checkedAt': now(), 'sshExitCode': response['sshExitCode'], 'transportUncertain': response['transportUncertain']}
        self.store.update(self.job['id'], desktopLaunch=self.value, phase='desktop_' + value['phase'])
        return self.value

    async def heartbeat(self):
        while not self.heartbeat_done.is_set():
            try:
                await asyncio.wait_for(self.heartbeat_done.wait(), 2)
                return
            except asyncio.TimeoutError: pass
            state = await self.owner.control.call('poll')
            self.owner.output(state)

    async def start(self):
        loop = asyncio.get_running_loop(); self.deadline = loop.time() + self.job['settings']['timeoutSeconds']
        wait_ms = min(DEFAULT_WAIT_MS, self.job['settings']['timeoutSeconds'] * 1000)
        text = command(self.deployment, self.job['settings']['arguments'], wait_ms)
        heartbeat = asyncio.create_task(self.heartbeat())
        launch = asyncio.create_task(self.query(text, wait_ms / 1000 + 5, starting=True))
        try:
            done, _ = await asyncio.wait((heartbeat, launch), return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done: await heartbeat
            value = await launch
        finally:
            # Do not cancel a sequenced controller call half way through a
            # response: the next call must never consume its predecessor's ACK.
            self.heartbeat_done.set()
            if not launch.done(): launch.cancel()
            await asyncio.gather(heartbeat, launch, return_exceptions=True)
        if self.force_status:
            latest = await self.query('DESKRUN /JSON /STATUS:' + self.key, 5)
            if latest: value = latest
        # Receipt retention is at most ~60 seconds and can be shorter. Reconcile
        # only this request, bounded by the original execution time limit.
        self.status_deadline = min(self.deadline, loop.time() + 45)
        while not value or not value['process_id']:
            # These explicit terminal rejections precede spawning in the native
            # broker/Desktop pipeline. Timeout/transport/lost service never
            # qualify as a rejection, even when no process ACK was received.
            if value and value['terminal'] and value['errorlevel'] in (2, 3, 4, 5, 6, 7):
                raise NotSubmitted('DESKRUN rejected the application start: ' + value['error'] + '.')
            if self.status_expired or loop.time() >= self.status_deadline:
                raise UnconfirmedGuestEffect('Launch outcome unknown: DESKRUN did not confirm an exact process identity. No launch was repeated.')
            await self.owner.control.call('poll')
            await asyncio.sleep(.5)
            value = await self.query('DESKRUN /JSON /STATUS:' + self.key, 5)
        self.process = (value['process_id'], value['process_generation'])
        # Do not reap Desktop-owned children or replace their native window ID.
        remaining = max(1, min(300, int(self.deadline - loop.time()) + 1))
        broker_id, broker_generation, _, _ = self.key.split(':')
        return await self.owner.control.call('adopt_desktop', instanceId=value['process_id'], generation=value['process_generation'],
            brokerInstanceId=int(broker_id), brokerGeneration=broker_generation, timeoutSeconds=remaining)

    async def refresh(self):
        loop = asyncio.get_running_loop()
        if (self.status_expired or loop.time() >= self.status_deadline or loop.time() < self.next_status
            or (self.value or {}).get('phase') == 'content' and not self.force_status):
            return
        self.next_status = loop.time() + 1
        value = await self.query('DESKRUN /JSON /STATUS:' + self.key, 5)
        if value and value['process_id'] and (value['process_id'], value['process_generation']) != self.process:
            raise UnconfirmedGuestEffect('DESKRUN status no longer names the adopted process generation.')

    def settled(self):
        return self.status_expired or asyncio.get_running_loop().time() >= self.status_deadline
