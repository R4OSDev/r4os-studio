"""Fixed private VM bridge client; no browser session or guest credentials here."""
import asyncio
import json
from contracts import DevelopmentFault, encode


async def vm_call(lease, operation, **fields):
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection('/run/r4os-studio-development/vm.sock', limit=262145), 5)
        writer.write((encode({'operation': operation, 'leaseId': lease.id, 'token': lease.token, **fields}) + '\n').encode()); await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 20)
        if len(raw) > 262144: raise DevelopmentFault('Private VM response exceeds the limit.', 503)
        value = json.loads(raw)
        if value.get('error'): raise DevelopmentFault(value['error'], value.get('code', 503))
        return value['result']
    except (OSError, asyncio.TimeoutError): raise DevelopmentFault('The private VM bridge is unavailable. Check development host support.', 503) from None
    finally:
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
