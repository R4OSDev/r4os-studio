"""Bounded run-owned processes with pipes or PTY. No web-process execution."""
import asyncio
import codecs
import errno
import os
from pathlib import Path
import pty
import signal
import uuid
from file_worker import parts
from run_store import event, item
from session_store import encode


class Process:
    def __init__(self, manager, ident, proc, master, cmd):
        self.manager = manager; self.id = ident; self.proc = proc; self.master = master
        self.pending = ''; self.dropped = False; self.bytes = 0; self.reason = None
        self.changed = asyncio.Event(); self.finished = asyncio.Event(); self.readers = []
        self.value = {'id': 'process-' + ident, 'runId': manager.worker.run_id, 'type': 'terminal',
                      'processId': ident, 'tool': 'studio.exec_command', 'arguments': {'cmd': cmd}, 'output': '', 'status': 'running'}
        self.publish()

    def publish(self):
        w = self.manager.worker
        item(w.store, w.session_id, w.run_id, self.value)

    def append(self, text):
        if not text: return
        self.bytes += len(text.encode())
        self.pending += text
        if len(self.pending.encode()) > 60000:
            self.pending = self.pending.encode()[-60000:].decode('utf8', 'ignore'); self.dropped = True
        visible = self.value['output']
        remaining = max(0, 120000-len(visible.encode()))
        if remaining:
            delta = text.encode()[:remaining].decode('utf8', 'ignore'); self.value['output'] += delta
            w = self.manager.worker
            w.store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                               (w.session_id, w.run_id, self.value['id'], encode(self.value)))
            event(w.store, w.session_id, w.run_id, 'delta', {'itemId': self.value['id'], 'text': delta, 'field': 'output'})
        if len(text.encode()) > remaining: self.value['truncated'] = True
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
        try:
            await asyncio.wait_for(asyncio.shield(self.proc.wait()), timeout/1000)
        except asyncio.TimeoutError: await self.terminate('timeout')
        # Namespace descendants keeping a pipe open must not delay cleanup.
        if self.readers:
            try: await asyncio.wait_for(asyncio.gather(*self.readers), 1)
            except asyncio.TimeoutError: pass
        self.close_master()
        code = self.proc.returncode
        self.value.update(status='completed' if code == 0 and not self.reason else 'failed', exitCode=code,
                          signal=-code if code is not None and code < 0 else None, reason=self.reason)
        self.publish(); self.finished.set(); self.changed.set()

    async def terminate(self, reason='terminated'):
        self.reason = self.reason or reason
        if self.proc.returncode is None:
            try: self.proc.terminate()
            except ProcessLookupError: pass
            try: await asyncio.wait_for(asyncio.shield(self.proc.wait()), 2)
            except asyncio.TimeoutError:
                try: self.proc.kill()
                except ProcessLookupError: pass
                await self.proc.wait()

    async def result(self, wait):
        if not self.pending and not self.finished.is_set():
            self.changed.clear()
            try: await asyncio.wait_for(self.changed.wait(), wait/1000)
            except asyncio.TimeoutError: pass
        # Wait a short scheduling turn so fast commands include an exit status.
        await asyncio.sleep(0.02)
        text, self.pending = self.pending, ''
        truncated, self.dropped = self.dropped, False
        return {'success': True, 'processId': self.id, 'state': 'exited' if self.finished.is_set() else 'running',
                'output': text, 'outputTruncated': truncated, 'exitCode': self.proc.returncode,
                'signal': -self.proc.returncode if self.proc.returncode is not None and self.proc.returncode < 0 else None, 'reason': self.reason}

    async def input(self, args):
        if self.finished.is_set():
            if args.get('chars'): return {'success': False, 'error': 'processExited', 'output': 'This process has exited.'}
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
            if written != len(value): return {'success': False, 'error': 'inputLimit', 'output': 'Terminal input was only partially accepted.'}
        elif self.proc.stdin and not self.proc.stdin.is_closing():
            try:
                if value: self.proc.stdin.write(value); await asyncio.wait_for(self.proc.stdin.drain(), 5)
                if args.get('closeStdin'): self.proc.stdin.close()
            except (BrokenPipeError, ConnectionResetError): pass
        elif value: return {'success': False, 'error': 'stdinClosed', 'output': 'Process input is closed.'}
        return await self.result(args.get('yield_time_ms', 1000))


class Terminals:
    def __init__(self, worker): self.worker = worker; self.processes = {}; self.tasks = set(); self.lock = asyncio.Lock()

    async def call(self, name, args):
        if name == 'exec_command':
            await self.worker.sandbox.prepare()
            async with self.lock:
                if sum(not p.finished.is_set() for p in self.processes.values()) >= 4 or len(self.processes) >= 32:
                    return {'success': False, 'error': 'processLimit', 'output': 'This run reached its process limit.'}
                names = parts(args.get('workdir', '.')); relative = '/'.join(names)
                # Inspect cwd within a file sandbox; host never follows a path
                # supplied by a command. Bubblewrap resolves it in its own root.
                checked = await self.worker.sandbox.file('list_directory', {'path': relative or '.'})
                if not checked['success']: return checked
                inner = ['/usr/bin/bash', '--noprofile', '--norc', '-c', args['cmd']]
                if args.get('tty'): inner = ['/usr/bin/setsid', '--ctty', '--wait', *inner]
                command = self.worker.sandbox.command(inner, '/workspace' + ('/' + relative if relative else ''))
                master = slave = None
                try:
                    if args.get('tty'):
                        master, slave = pty.openpty(); os.set_blocking(master, False)
                    proc = await asyncio.create_subprocess_exec(*command,
                        stdin=slave if slave is not None else asyncio.subprocess.PIPE,
                        stdout=slave if slave is not None else asyncio.subprocess.PIPE,
                        stderr=slave if slave is not None else asyncio.subprocess.PIPE,
                        start_new_session=True)
                except BaseException:
                    if master is not None: os.close(master)
                    raise
                finally:
                    if slave is not None: os.close(slave)
                ident = str(uuid.uuid4()); process = Process(self, ident, proc, master, args['cmd']); self.processes[ident] = process
                if master is None:
                    process.readers = [asyncio.create_task(process.pipe(stream)) for stream in (proc.stdout, proc.stderr)]
                else:
                    process.decoder = codecs.getincrementaldecoder('utf8')('replace')
                    asyncio.get_running_loop().add_reader(master, process.pty_read)
                task = asyncio.create_task(process.watch(args.get('timeout_ms', 120000)))
                self.tasks.add(task); task.add_done_callback(self.tasks.discard)
            return await process.result(args.get('yield_time_ms', 1000))
        process = self.processes.get(args['processId'])
        if process is None: return {'success': False, 'error': 'unknownProcess', 'output': 'This handle does not belong to an active process in this run.'}
        if name == 'write_stdin': return await process.input(args)
        if name == 'terminate_process':
            await process.terminate(); await process.finished.wait(); return await process.result(100)
        raise ValueError('Unknown terminal tool.')

    async def close(self):
        await asyncio.gather(*(p.terminate('runEnded') for p in self.processes.values() if not p.finished.is_set()), return_exceptions=True)
        if self.tasks: await asyncio.gather(*self.tasks, return_exceptions=True)
