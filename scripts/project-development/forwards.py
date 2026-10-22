"""Retire only this VM's stale private forwarding/secret receipts under its lock."""
import json
from pathlib import Path
import shutil
from contracts import DevelopmentFault, identity
from lease import birth
from layout import save
from jobs import now
from vm_client import vm_call
RUNTIME = Path('/run/r4os-studio-development/auth')


async def cleanup(lease):
    directory = lease.root / 'Forwards'
    if not directory.exists(): return []
    records = []
    for path in directory.glob('*.json'):
        if path.resolve(strict=True) != path or path.stat().st_size > 16384: raise DevelopmentFault('Invalid forwarding recovery receipt.', 503)
        value = json.loads(path.read_text())
        if value.get('vmId') != lease.vm_id or value.get('state') == 'closed' or value.get('leaseId') == lease.id: continue
        old_id = identity(value['leaseId'])
        if path.name != old_id + '.json' or type(value.get('port')) is not int or not 1024 <= value['port'] <= 65535:
            raise DevelopmentFault('Invalid forwarding identity.', 503)
        owner_path = lease.root / 'leases' / (old_id + '.json')
        if owner_path.resolve(strict=True) != owner_path: raise DevelopmentFault('Invalid old forwarding owner.', 503)
        owner = json.loads(owner_path.read_text())
        if owner['vmId'] != lease.vm_id or owner['scope'] != value['scope']: raise DevelopmentFault('The forwarding owner differs from its reservation.', 503)
        live = False
        try: live = owner['closedAt'] is None and birth(owner['pid']) == owner['birth']
        except OSError: pass
        if live: continue
        records.append((path, value))
    if not records: return []
    info = await vm_call(lease, 'info'); recovered = []
    for path, value in records:
        if info['vm']['state'] != 'stopped':
            if info['vm']['state'] != 'running': raise DevelopmentFault('Wait for a stable VM state before recovering forwarding.')
            await vm_call(lease, 'forward_close', port=value['port'])
        runtime = RUNTIME / value['leaseId']
        if runtime.exists():
            if runtime.resolve(strict=True) != runtime: raise DevelopmentFault('Invalid private authentication recovery directory.', 503)
            shutil.rmtree(runtime)
        save(path, {**value, 'state': 'closed', 'recoveredAt': now(), 'reason': 'stale reservation; exact forwarding removed or VM stopped'})
        recovered.append(value['leaseId'])
    return recovered
