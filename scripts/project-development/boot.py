"""Private QMP reset observer, independent of the browser/model process."""
import asyncio
import datetime
import json
import os
from pathlib import Path
import sys
import uuid

from contracts import DevelopmentFault, identity
from jobs import folder, now
from layout import save
from lease import birth


def saved_boot(projects, vm_id):
    file = Path(projects) / '.studio/development/Boots' / (identity(vm_id) + '.json')
    try:
        if file.resolve(strict=True) != file or file.stat().st_size > 16384: return None
        value = json.loads(file.read_text())
        if isinstance(value, dict) and value.get('vmId') == vm_id: return value
    except (OSError, ValueError): pass


def event_time(message):
    stamp = message.get('timestamp') or {}
    seconds, micros = stamp.get('seconds'), stamp.get('microseconds')
    if type(seconds) is int and type(micros) is int and 0 <= micros < 1000000:
        try: return datetime.datetime.fromtimestamp(seconds, datetime.UTC).replace(microsecond=micros).isoformat()
        except (OverflowError, OSError, ValueError): pass
    return now()


class BootWatch:
    def __init__(self, projects):
        self.projects = Path(projects)
        self.root = folder(self.projects / '.studio/development/Boots')
        self.tasks = {}; self.values = {}; self.connected = {}

    def previous(self, vm):
        value = self.values.get(vm['id']) or saved_boot(self.projects, vm['id'])
        if value and all(value.get(key) == vm[source] for key, source in
                         (('vmRevision', 'revision'), ('imageId', 'imageId'), ('imageSha256', 'imageSha256'))):
            return value
        return {}

    def write(self, vm, invocation, connected, new=False, *, running=False, transition=None):
        old = self.previous(vm)
        value = {'schema': 1, 'vmId': vm['id'], 'vmRevision': vm['revision'], 'imageId': vm['imageId'],
            'imageSha256': vm['imageSha256'], 'invocationId': invocation, 'connected': connected, 'running': running,
            'bootId': str(uuid.uuid4()) if new or not old else old['bootId'], 'observedAt': now(),
            'pid': os.getpid(), 'birth': birth(os.getpid())}
        if transition is not None:
            value['transition'] = {**transition, 'bootId':value['bootId'], 'invocationId':invocation}
        elif old.get('invocationId') == invocation and old.get('transition'):
            value['transition'] = old['transition']
        if transition and transition['kind']=='qmp_reset' and transition.get('guest') is False:
            value['hostReset'] = value['transition']
        elif old.get('invocationId') == invocation and old.get('hostReset'):
            value['hostReset'] = old['hostReset']
        if not connected:
            if old.get('connected'):
                value['lastConnected'] = {key:old[key] for key in ('bootId','invocationId')}
            elif old.get('lastConnected'):
                value['lastConnected'] = old['lastConnected']
        save(self.root / (vm['id'] + '.json'), value)
        self.values[vm['id']] = value
        status = self.connected.setdefault(vm['id'], asyncio.Event())
        if connected and value.get('transition'):
            from quarantine import resolve_after_boot
            try: resolve_after_boot(self.projects, value)
            except (DevelopmentFault, OSError, ValueError, KeyError, TypeError):
                print('The VM boot was confirmed, but its recovery record could not be resolved.', file=sys.stderr)
        if connected: status.set()
        else: status.clear()
        return value

    async def ensure(self, vm, invocation, *, allow_paused=False):
        identity(vm['id'])
        deadline = asyncio.get_running_loop().time() + 8
        old = self.values.get(vm['id']); task = self.tasks.get(vm['id'])
        if not task or task.done() or not old or old['vmRevision'] != vm['revision'] or old['invocationId'] != invocation:
            if task and not task.done(): task.cancel(); await asyncio.gather(task, return_exceptions=True)
            ready = asyncio.get_running_loop().create_future()
            self.tasks[vm['id']] = asyncio.create_task(self.observe(vm, invocation, ready))
            await asyncio.wait_for(ready, 8)
        while not self.values[vm['id']]['connected'] and not self.tasks[vm['id']].done():
            try: await asyncio.wait_for(self.connected[vm['id']].wait(), max(0, deadline-asyncio.get_running_loop().time()))
            except asyncio.TimeoutError: break
        value = self.values[vm['id']]
        if not value['connected'] or (not allow_paused and not value['running']):
            raise DevelopmentFault('The VM boot state is not confirmed. Check access again.')
        return value

    async def observe(self, vm, invocation, ready):
        previous = self.previous(vm)
        previous = previous.get('lastConnected') or previous
        transition = None
        if previous.get('invocationId') and previous['invocationId'] != invocation:
            transition = {'kind':'new_instance','previousBootId':previous['bootId'],
                          'previousInvocationId':previous['invocationId'],'observedAt':now()}
        writer = None; self.write(vm, invocation, False, True)
        try:
            if not isinstance(invocation, str) or len(invocation) != 32: raise DevelopmentFault('The VM service invocation is not active.')
            runtime = Path(os.environ.get('STUDIO_VM_RUNTIME_DIR', '/run/r4os-studio-vms'))
            socket = runtime / identity(vm['id']) / 'development-qmp.sock'
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(socket, limit=1048577), 5)
            stage = 'greeting'; sequence = 0; state_id = None

            def query_state():
                nonlocal sequence, state_id
                sequence += 1; state_id = 'state-' + str(sequence)
                writer.write((json.dumps({'execute':'query-status','id':state_id})+'\n').encode())

            while True:
                raw = await reader.readline()
                if not raw or len(raw) > 1048576: raise DevelopmentFault('The VM monitor disconnected.')
                message = json.loads(raw)
                if 'QMP' in message and stage == 'greeting':
                    writer.write(b'{"execute":"qmp_capabilities","id":"cap"}\n'); stage = 'cap'
                elif message.get('id') == 'cap':
                    if 'error' in message: raise DevelopmentFault('VM monitor negotiation failed.')
                    query_state(); stage = 'observing'
                elif state_id is not None and message.get('id') == state_id:
                    running = message.get('return', {}).get('running')
                    if type(running) is not bool: raise DevelopmentFault('The VM monitor did not confirm its state.')
                    value = self.write(vm, invocation, True, running=running, transition=transition)
                    transition = None; state_id = None
                    if not ready.done(): ready.set_result(value)
                elif stage == 'observing' and message.get('event') in ('RESET', 'SHUTDOWN', 'STOP', 'RESUME'):
                    event = message['event']
                    reset = None
                    if event == 'RESET':
                        current = self.values[vm['id']]
                        before = current.get('lastConnected') or current
                        reset = {'kind':'qmp_reset','previousBootId':before['bootId'],
                                 'previousInvocationId':invocation,'observedAt':now(),'resetAt':event_time(message),
                                 'guest':(message.get('data') or {}).get('guest')}
                        transition = None
                    self.write(vm, invocation, False, True, transition=reset)
                    if event == 'SHUTDOWN':
                        transition = None; state_id = None
                    else: query_state()
                await writer.drain()
        except BaseException:
            self.write(vm, invocation, False, True)
            if not ready.done(): ready.set_exception(DevelopmentFault('The development monitor is unavailable. Stop and start this VM to enable it.'))
        finally:
            if writer:
                writer.close()
                try: await writer.wait_closed()
                except Exception: pass

    async def close(self):
        for task in self.tasks.values(): task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
