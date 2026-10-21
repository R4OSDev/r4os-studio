"""Private QMP reset observer, independent of the browser/model process."""
import asyncio
import json
import os
from pathlib import Path
import uuid

from contracts import DevelopmentFault, identity, encode
from jobs import folder, now
from layout import save
from lease import birth


class BootWatch:
    def __init__(self, projects): self.root = folder(Path(projects) / '.studio/development/Boots'); self.tasks = {}; self.values = {}

    def write(self, vm, invocation, connected, new=False):
        old = self.values.get(vm['id'])
        value = {'schema': 1, 'vmId': vm['id'], 'vmRevision': vm['revision'], 'imageId': vm['imageId'],
            'imageSha256': vm['imageSha256'], 'invocationId': invocation, 'connected': connected,
            'bootId': str(uuid.uuid4()) if new or not old else old['bootId'], 'observedAt': now(),
            'pid': os.getpid(), 'birth': birth(os.getpid())}
        self.values[vm['id']] = value; save(self.root / (vm['id'] + '.json'), value); return value

    async def ensure(self, vm, invocation):
        identity(vm['id'])
        old = self.values.get(vm['id']); task = self.tasks.get(vm['id'])
        if not task or task.done() or not old or old['vmRevision'] != vm['revision'] or old['invocationId'] != invocation:
            if task and not task.done(): task.cancel(); await asyncio.gather(task, return_exceptions=True)
            ready = asyncio.get_running_loop().create_future()
            self.tasks[vm['id']] = asyncio.create_task(self.observe(vm, invocation, ready))
            await asyncio.wait_for(ready, 8)
        value = self.values[vm['id']]
        if not value['connected']: raise DevelopmentFault('The VM boot state is not confirmed. Check access again.')
        return value

    async def observe(self, vm, invocation, ready):
        writer = None; self.write(vm, invocation, False, True)
        try:
            if not isinstance(invocation, str) or len(invocation) != 32: raise DevelopmentFault('The VM service invocation is not active.')
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection('/run/r4os-studio-vms/' + identity(vm['id']) + '/development-qmp.sock', limit=1048577), 5)
            stage = 'greeting'
            while True:
                raw = await reader.readline()
                if not raw or len(raw) > 1048576: raise DevelopmentFault('The VM monitor disconnected.')
                message = json.loads(raw)
                if 'QMP' in message and stage == 'greeting':
                    writer.write(b'{"execute":"qmp_capabilities","id":"cap"}\n'); stage = 'cap'
                elif message.get('id') == 'cap':
                    if 'error' in message: raise DevelopmentFault('VM monitor negotiation failed.')
                    writer.write(b'{"execute":"query-status","id":"state"}\n'); stage = 'state'
                elif message.get('id') == 'state':
                    if not message.get('return', {}).get('running'): raise DevelopmentFault('The VM is not running.')
                    value = self.write(vm, invocation, True)
                    if not ready.done(): ready.set_result(value)
                    stage = 'observing'
                elif message.get('event') in ('RESET', 'SHUTDOWN', 'STOP', 'RESUME'):
                    self.write(vm, invocation, False, True)
                    if message['event'] in ('RESET', 'RESUME'):
                        writer.write(b'{"execute":"query-status","id":"state"}\n')
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
