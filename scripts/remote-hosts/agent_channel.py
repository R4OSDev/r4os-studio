"""Separate fixed socket accepts exactly one inherited SCM_RIGHTS lease."""
import asyncio
import json
import os
import socket
import socketserver
import struct
import threading
from catalog import CatalogFault


def start(host, path, loop):
    slots = threading.BoundedSemaphore(16)
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            if not slots.acquire(blocking=False): return
            descriptors = []; self.request.settimeout(5)
            try:
                peer_pid, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != host.config['uid']: raise CatalogFault('This remote peer is not authorized.', 403)
                raw = b''
                while b'\n' not in raw:
                    part, controls, flags, _ = self.request.recvmsg(32768, socket.CMSG_SPACE(16))
                    for level, kind, value in controls:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS: descriptors.extend(struct.unpack(str(len(value)//4) + 'i', value))
                    if flags & socket.MSG_CTRUNC or len(descriptors) > 1 or not part or len(raw) + len(part) > 32768:
                        raise CatalogFault('Invalid inherited remote lease frame.', 400)
                    raw += part
                if len(descriptors) != 1: raise CatalogFault('The original workspace lease is required.', 403)
                future = asyncio.run_coroutine_threadsafe(host.agent_request(json.loads(raw), descriptors[0], peer_pid), loop)
                result = future.result(timeout=10); reply = {'result': result}
            except CatalogFault as error: reply = {'error': str(error), 'code': error.code}
            except Exception: reply = {'error': 'The original remote request could not be confirmed. Retain its request ID.', 'code': 503}
            finally:
                for descriptor in descriptors: os.close(descriptor)
                slots.release()
            try: self.request.sendall(json.dumps(reply, ensure_ascii=True).encode() + b'\n')
            except OSError: pass
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True; request_queue_size = 16
    if path.exists() or path.is_symlink():
        if not path.is_socket() or path.is_symlink(): raise CatalogFault('Invalid original remote agent socket.', 503)
        path.unlink()
    server = Server(str(path), Handler); path.chmod(0o600)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .1}, daemon=True); thread.start()
    return server
