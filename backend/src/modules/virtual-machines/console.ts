import { randomBytes } from 'node:crypto';
import { createConnection } from 'node:net';
import { join } from 'node:path';
import { createWebSocketStream, WebSocket } from 'ws';
import { runtimePath, VmError } from './paths.js';

/** Short-lived, single-use grants are sent in a WebSocket subprotocol, never a URL. */
export class ConsoleTickets {
  private grants = new Map<string, { vm: string; owner: string; channel: 'display' | 'pointer'; expires: number }>();
  issue(vm: string, owner: string, channel: 'display' | 'pointer' = 'display') {
    for (const [key, grant] of this.grants) if (grant.expires <= Date.now()) this.grants.delete(key);
    if (this.grants.size >= 256) throw new VmError('Too many pending console connections. Try again shortly.', 429);
    const ticket = randomBytes(32).toString('hex');
    this.grants.set(ticket, { vm, owner, channel, expires: Date.now() + 20_000 });
    return ticket;
  }
  consume(vm: string, owner: string, protocols: string | undefined, channel: 'display' | 'pointer' = 'display') {
    const ticket = protocols?.split(',').map((part) => part.trim()).find((part) => /^studio-ticket\.[a-f0-9]{64}$/.test(part))?.slice(14);
    const grant = ticket && this.grants.get(ticket);
    if (!grant || grant.expires <= Date.now() || grant.vm !== vm || grant.owner !== owner || grant.channel !== channel) throw new VmError('Reload the console before reconnecting.', 403);
    this.grants.delete(ticket);
  }
}

/** One RFB byte stream per client; QEMU listens only on its private Unix socket. */
export class ConsoleBridge {
  private peers = new Set<{ id: string; websocket: WebSocket; close: () => void }>();
  attach(id: string, websocket: WebSocket) {
    if (this.peers.size >= 32 || [...this.peers].filter((peer) => peer.id === id).length >= 2) {
      websocket.close(1013, 'Too many console connections. Close another console and reconnect.'); return;
    }
    const upstream = createConnection(join(runtimePath(id), 'vnc.sock'));
    const stream = createWebSocketStream(websocket, { highWaterMark: 64 * 1024 });
    let closed = false, alive = true;
    const connectTimer = setTimeout(() => websocket.close(1011, 'The VM display is not ready.'), 5000);
    const heartbeat = setInterval(() => {
      if (!alive || websocket.bufferedAmount > 8 * 1024 * 1024) { peer.close(); return; }
      alive = false; if (websocket.readyState === WebSocket.OPEN) websocket.ping();
    }, 30_000);
    heartbeat.unref();
    const peer = { id, websocket, close: () => {
      if (closed) return; closed = true; clearTimeout(connectTimer); clearInterval(heartbeat);
      upstream.destroy(); stream.destroy(); websocket.terminate(); this.peers.delete(peer);
    } };
    this.peers.add(peer);
    websocket.on('pong', () => { alive = true; });
    websocket.on('close', peer.close); websocket.on('error', peer.close);
    stream.on('error', peer.close);
    upstream.on('error', () => { websocket.close(1011, 'The VM display is unavailable. Stop and start the VM if necessary.'); upstream.destroy(); });
    upstream.on('close', () => { if (!closed) { websocket.close(1000, 'VM display disconnected.'); peer.close(); } });
    upstream.on('connect', () => {
      clearTimeout(connectTimer); upstream.pipe(stream); stream.pipe(upstream);
    });
  }
  close() { for (const peer of this.peers) peer.close(); }
}
