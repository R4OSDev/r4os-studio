"""Bounded run-owned processes with pipes or PTY. No web-process execution."""
import asyncio
import codecs
import errno
import json
import os
from pathlib import Path
import pty
import sqlite3
import uuid
from run_store import event, item, get_run
from store import ProjectFault
from terminal_timing import Timing, retained as retained_timing, unknown as unknown_timing
from terminal_group import Group
from text_budget import bounded_text, TextBuffer


class Process:
    def __init__(self, manager, ident, proc, master, cmd, timing=None):
        self.manager = manager; self.id = ident; self.proc = proc; self.master = master
        self.timing=timing or Timing();self.timing.bind_process(proc)
        self.group = Group(proc.pid, self.timing.birth)
        self.stop_lock = asyncio.Lock()
        self.pending_buffer = TextBuffer(60000, True); self.output_buffer = TextBuffer(120000)
        self.dropped = False; self.bytes = 0; self.reason = None
        self.changed = asyncio.Event(); self.finished = asyncio.Event(); self.exited = asyncio.Event(); self.readers = []
        self.io_lock = asyncio.Lock()
        self.value = {'id': 'process-' + ident, 'runId': manager.worker.run_id, 'type': 'terminal',
                      'processId': ident, 'tool': 'studio.exec_command', 'arguments': {'cmd': cmd}, 'output': '', 'status': 'running'}
        self.publish()
        self.exit_observer=asyncio.create_task(self.observe_exit())

    @property
    def pending(self):return self.pending_buffer.value

    @pending.setter
    def pending(self,value):
        self.pending_buffer = TextBuffer(60000, True)
        self.pending_buffer.append(value)

    def publish(self):
        self.refresh_timing()
        w = self.manager.worker
        item(w.store, w.session_id, w.run_id, self.value)

    def refresh_timing(self):
        if self.proc.returncode is not None:self.timing.end()
        self.value.update(self.timing.public(),terminalTiming=self.timing.proof())

    def timed_error(self,error,output):
        self.publish()
        return {'success':False,'error':error,'output':output,'processId':self.id,**self.timing.public()}

    async def observe_exit(self):
        # A descendant holding a pipe open must not inflate the parent's measured
        # lifetime. This observes returncode only and changes no watchdog policy.
        while self.proc.returncode is None and not self.finished.is_set():
            await asyncio.sleep(.05)
        if self.proc.returncode is not None:
            self.timing.end()
            self.exited.set()
            try:self.publish()
            except (OSError,sqlite3.Error,ProjectFault):pass  # Normal final/poll publication remains authoritative.

    def append(self, text):
        if not text: return
        self.refresh_timing()
        self.bytes += len(text.encode())
        _, clipped = self.pending_buffer.append(text)
        self.dropped = self.dropped or clipped
        delta, clipped = self.output_buffer.append(text)
        if delta:
            self.value['output'] = self.output_buffer.value
            w = self.manager.worker
            from public_stream import delta as public_delta
            public_delta(w.store, w.session_id, w.run_id, self.value, {'itemId': self.value['id'], 'text': delta, 'field': 'output'})
        if clipped: self.value['truncated'] = True
        self.changed.set()
        if self.bytes > 2*1024*1024 and self.reason is None:
            self.reason = 'outputLimit'; asyncio.create_task(self.terminate('outputLimit'))

    async def pipe(self, stream):
        decoder = codecs.getincrementaldecoder('utf8')('replace')
        try:
            while chunk := await stream.read(8192): self.append(decoder.decode(chunk))
            self.append(decoder.decode(b'', final=True))
        except (OSError, asyncio.CancelledError): pass

    def pty_read(self):
        try:
            data = os.read(self.master, 8192)
            if data: self.append(self.decoder.decode(data)); return
        except BlockingIOError: return
        except OSError as e:
            if e.errno != errno.EIO: self.reason = self.reason or 'ioError'
        self.close_master()

    def close_master(self):
        if self.master is not None:
            asyncio.get_running_loop().remove_reader(self.master)
            self.append(self.decoder.decode(b'', final=True)); os.close(self.master); self.master = None

    async def watch(self, timeout):
        self.timing.bind_limit(timeout)
        try:
            if self.proc.returncode is None:
                await asyncio.wait_for(self.exited.wait(), self.timing.remaining_seconds())
        except asyncio.TimeoutError: await self.terminate('timeout')
        if self.proc.returncode is not None:self.timing.end()
        # Also retire children after an ordinary shell exit. A finished handle
        # must not leave a background command running in the workspace.
        if not self.finished.is_set():
            async with self.stop_lock:
                self.value['processEndConfirmed'] = await self.group.stop()
        if not self.value.get('processEndConfirmed'):
            self.reason = self.reason or 'cleanupUnconfirmed'
        if self.readers:
            try: await asyncio.wait_for(asyncio.gather(*self.readers), 1)
            except asyncio.TimeoutError: pass
        self.close_master()
        code = self.proc.returncode
        self.value.update(status='completed' if code == 0 and not self.reason else 'failed', exitCode=code,
                          signal=-code if code is not None and code < 0 else None, reason=self.reason)
        try: self.publish()
        finally:
            self.finished.set();self.changed.set()
            self.exit_observer.cancel()
            await asyncio.gather(self.exit_observer,return_exceptions=True)

    async def terminate(self, reason='terminated'):
        self.reason = self.reason or reason
        async with self.stop_lock:
            self.value['processEndConfirmed'] = await self.group.stop()
            try: await asyncio.wait_for(asyncio.shield(self.proc.wait()), 1)
            except asyncio.TimeoutError: self.value['processEndConfirmed'] = False
        if self.proc.returncode is not None:self.timing.end()

    async def result(self, wait):
        if not self.pending and not self.finished.is_set():
            self.changed.clear()
            try: await asyncio.wait_for(self.changed.wait(), wait/1000)
            except asyncio.TimeoutError: pass
        # Wait a short scheduling turn so fast commands include an exit status.
        await asyncio.sleep(0.02)
        return self.collect()

    async def wait_result(self, watcher, *, interrupted=False):
        try:
            if not interrupted:
                await asyncio.shield(watcher)
        except asyncio.CancelledError:
            interrupted = True
        if interrupted:
            await self.terminate('interrupted')
            await asyncio.shield(watcher)
        result = self.collect()
        if result['processEndConfirmed'] is not True or result['exitCode'] is None:
            return {**result, 'success': False, 'state': 'unknown', 'error': 'unknown',
                    'partialChangesPossible': True}
        if interrupted:
            return {**result, 'success': False, 'error': 'interrupted', 'partialChangesPossible': True}
        return result

    def collect(self):
        text, self.pending = self.pending, ''
        truncated, self.dropped = self.dropped, False
        self.publish()
        return {'success': True, 'processId': self.id, 'state': 'exited' if self.finished.is_set() else 'running',
                'output': text, 'outputTruncated': truncated, 'exitCode': self.proc.returncode,
                'signal': -self.proc.returncode if self.proc.returncode is not None and self.proc.returncode < 0 else None, 'reason': self.reason,
                'processEndConfirmed': self.value.get('processEndConfirmed') if self.finished.is_set() else None,
                **self.timing.public()}

    async def input(self, args):
        if self.finished.is_set():
            if args.get('chars'): return self.timed_error('processExited','This process has exited.')
            return await self.result(100)
        value = args.get('chars', '').encode()
        if self.master is not None:
            if args.get('closeStdin'): value += b'\x04'
            # PTY writes are bounded and nonblocking; partial input is reported.
            written = 0
            for _ in range(500):
                try: written += os.write(self.master, value[written:])
                except BlockingIOError: pass
                if written == len(value): break
                await asyncio.sleep(0.01)
            if written != len(value): return self.timed_error('inputLimit','Terminal input was only partially accepted.')
        elif self.proc.stdin and not self.proc.stdin.is_closing():
            try:
                if value: self.proc.stdin.write(value); await asyncio.wait_for(self.proc.stdin.drain(), 5)
                if args.get('closeStdin'): self.proc.stdin.close()
            except (BrokenPipeError, ConnectionResetError): pass
        elif value: return self.timed_error('stdinClosed','Process input is closed.')
        return await self.result(args.get('yield_time_ms', 1000))


class Terminals:
    def __init__(self, worker): self.worker = worker; self.processes = {}; self.tasks = set(); self.lock = asyncio.Lock()

    async def call(self, name, args):
        if name == 'exec_command':
            try: await self.worker.workspace_tools.prepare()
            except (OSError, ValueError, ProjectFault) as error:
                return {'success': False, 'error': 'preparationFailed', 'output': str(error) if isinstance(error, ProjectFault) else 'The workspace environment is unavailable. No command started.'}
            config = getattr(self.worker, 'config', {})
            foreground = config.get('terminalCompletion') == 1
            resumable = not foreground or bool(args.get('tty')) or 'yield_time_ms' in args
            from tool_deadlines import seconds_for
            deadline = seconds_for(config, 'studio.exec_command')
            limit_ms = args.get('timeout_ms', deadline * 1000 if deadline is not None else 120000)
            if deadline is not None:
                limit_ms = min(limit_ms, deadline * 1000)
            async with self.lock:
                if sum(not p.finished.is_set() for p in self.processes.values()) >= 4:
                    return {'success': False, 'error': 'processLimit', 'output': 'This run reached its process limit.'}
                # Bound live bookkeeping, not the number of commands across a
                # multi-day Goal. Keep undelivered output; final status remains
                # available from the run-owned durable terminal item.
                for ident, process in tuple(self.processes.items()):
                    if len(self.processes) < 32: break
                    if process.finished.is_set() and not process.pending: del self.processes[ident]
                if len(self.processes) >= 32:
                    return {'success': False, 'error': 'processLimit', 'output': 'Collect pending terminal output before starting another process.'}
                workdir = args.get('workdir', '.')
                admitted = get_run(self.worker.store, self.worker.run_id)
                if getattr(self.worker, 'stopping', False) or not admitted['busy'] or admitted['state'] == 'stopping':
                    return {'success': False, 'error': 'interrupted', 'output': 'The run stopped before the command started.'}
                inner = ['/usr/bin/bash', '--noprofile', '--norc', '-c', args['cmd']]
                if args.get('tty'):
                    inner = ['/usr/bin/python3', '-I', '-B', str(Path(__file__).with_name('terminal_pty.py')), *inner]
                command = self.worker.workspace_tools.command(inner, workdir)
                master = slave = None
                interrupted = False
                try:
                    if args.get('tty'):
                        master, slave = pty.openpty(); os.set_blocking(master, False)
                    timing=Timing(limit_ms)
                    stdin = asyncio.subprocess.PIPE if resumable else asyncio.subprocess.DEVNULL
                    spawn = asyncio.create_task(asyncio.create_subprocess_exec(*command,
                        stdin=slave if slave is not None else stdin,
                        stdout=slave if slave is not None else asyncio.subprocess.PIPE,
                        stderr=slave if slave is not None else asyncio.subprocess.PIPE,
                        start_new_session=True))
                    try:
                        proc = await asyncio.shield(spawn)
                    except asyncio.CancelledError:
                        interrupted = True
                        proc = await spawn
                except BaseException:
                    if master is not None: os.close(master)
                    raise
                finally:
                    if slave is not None: os.close(slave)
                ident = str(uuid.uuid4()); process = Process(self, ident, proc, master, args['cmd'],timing=timing); self.processes[ident] = process
                if master is None:
                    process.readers = [asyncio.create_task(process.pipe(stream)) for stream in (proc.stdout, proc.stderr)]
                else:
                    process.decoder = codecs.getincrementaldecoder('utf8')('replace')
                    asyncio.get_running_loop().add_reader(master, process.pty_read)
                task = asyncio.create_task(process.watch(limit_ms))
                self.tasks.add(task); task.add_done_callback(self.tasks.discard)
            if resumable and not interrupted:
                try:
                    return await process.result(args.get('yield_time_ms', 1000))
                except asyncio.CancelledError:
                    interrupted = True
            return await process.wait_result(task, interrupted=interrupted)
        process = self.processes.get(args['processId'])
        if process is None:
            worker = self.worker
            row = worker.store.db.execute('SELECT payload FROM items WHERE session_id=? AND run_id=? AND item_id=?',
                (worker.session_id, worker.run_id, 'process-' + args['processId'])).fetchone()
            value = json.loads(row[0]) if row else {}
            owned=value.get('type')=='terminal' and value.get('processId')==args['processId'] and value.get('runId')==worker.run_id
            if not owned or value.get('status') not in ('completed', 'failed'):
                return {'success': False, 'error': 'unknownProcess', 'output': 'This handle does not belong to an active process in this run.',
                    **(retained_timing(value) if owned else unknown_timing())}
            if name == 'write_stdin' and args.get('chars'):
                return {'success': False, 'error': 'processExited', 'output': 'This process has exited.','processId':args['processId'],**retained_timing(value)}
            return {'success': True, 'processId': args['processId'], 'state': 'exited', 'output': '', 'outputTruncated': False,
                'exitCode': value.get('exitCode'), 'signal': value.get('signal'), 'reason': value.get('reason'),
                'processEndConfirmed': value.get('processEndConfirmed'), **retained_timing(value)}
        async with process.io_lock:
            if name == 'write_stdin': return await process.input(args)
            if name == 'terminate_process':
                await process.terminate(); await process.finished.wait(); return await process.result(100)
        raise ValueError('Unknown terminal tool.')

    async def close(self):
        await asyncio.gather(*(p.terminate('runEnded') for p in self.processes.values() if not p.finished.is_set()), return_exceptions=True)
        if self.tasks: await asyncio.gather(*self.tasks, return_exceptions=True)
