"""Fixed private VM bridge client; no browser session or guest credentials here."""
import asyncio
import json
import os
from contracts import DevelopmentFault, LIMITS, encode


async def vm_call(lease, operation, **fields):
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(os.environ.get('STUDIO_DEVELOPMENT_VM_SOCKET', '/run/r4os-studio-development/vm.sock'), limit=2097153), 5)
        writer.write((encode({'operation': operation, 'leaseId': lease.id, 'token': lease.token, **fields}) + '\n').encode()); await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 20)
        if len(raw) > 2097152: raise DevelopmentFault('Private VM response exceeds the limit.', 503)
        value = json.loads(raw)
        if value.get('error'): raise DevelopmentFault(value['error'], value.get('code', 503))
        if operation in ('capture_original', 'capture_diagnostic'):
            length = value.get('result', {}).get('bytes')
            if type(length) is not int or not 0 < length <= LIMITS['screenshotOriginalBytes']:
                raise DevelopmentFault('The original VM screenshot has an invalid byte length.', 503)
            try: return await asyncio.wait_for(reader.readexactly(length), 20)
            except asyncio.IncompleteReadError:
                raise DevelopmentFault('The original VM screenshot transfer was incomplete.', 503) from None
        return value['result']
    except (OSError, asyncio.TimeoutError): raise DevelopmentFault('The private VM bridge is unavailable. Check development host support.', 503) from None
    finally:
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
