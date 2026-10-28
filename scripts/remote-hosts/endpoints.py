"""Pin resolved SSH peers and serialize effects across catalog DNS/IP aliases."""
import asyncio
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
from catalog import CatalogFault, regular
from transport import private_directory


def address(value):
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped: ip = ip.ipv4_mapped
    return str(ip)


async def resolve(host):
    try: values = [address(host['address'])]
    except ValueError:
        try:
            results = await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, host['address'], host['port'], 0, socket.SOCK_STREAM), 5)
            values = sorted({address(row[4][0]) for row in results if row[0] in (socket.AF_INET, socket.AF_INET6) and (len(row[4]) < 4 or row[4][3] == 0)})
        except (OSError, ValueError, asyncio.TimeoutError): raise CatalogFault('The saved Remote Host address could not be resolved within its deadline.', 503) from None
    if not values or len(values) > 16: raise CatalogFault('The saved Remote Host has no bounded qualified IP destination.', 503)
    values = sorted(set(values), key=lambda text: (ipaddress.ip_address(text).version, text))
    return {'address': host['address'], 'port': host['port'], 'addresses': values, 'connectAddress': values[0]}


def overlaps(first, second):
    if first.get('port') != second.get('port'): return False
    return first.get('address') == second.get('address') or bool(set(first.get('addresses', [])) & set(second.get('addresses', [])))


class Reservation:
    def __init__(self, runtime, identity, effect):
        self.descriptors = []; root = private_directory(Path(runtime) / 'endpoint-locks')
        keys = [('name', identity['address'], identity['port']), *[('ip', ip, identity['port']) for ip in identity['addresses']]]
        try:
            if effect:
                count = sum(1 for _ in root.iterdir())
                for key in sorted(set(keys)):
                    name = hashlib.sha256(json.dumps(key).encode()).hexdigest() + '.lock'
                    if not (root / name).exists():
                        if count >= 8192: raise CatalogFault('Endpoint lock history needs local maintenance.', 503)
                        count += 1
                    descriptor = os.open(root / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600); self.descriptors.append(descriptor); regular(root / name)
                    try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError: raise CatalogFault('This resolved SSH endpoint already has an active Studio effect. Inspect the original job; no second effect was sent.', 409) from None
            # Read-only diagnostics remain independent of an active effect, with
            # the broker's existing four-job/four-check global admission bounds.
        except BaseException: self.close(); raise

    def close(self):
        for descriptor in self.descriptors: os.close(descriptor)
        self.descriptors.clear()
