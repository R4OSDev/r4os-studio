import { randomBytes } from 'node:crypto';
import { createConnection } from 'node:net';
import { join } from 'node:path';
import { createWebSocketStream, WebSocket } from 'ws';
import { runtimePath, VmError } from './paths.js';
import type { VmConsoleMode } from '../../../../shared/virtual-machines.js';
import { SpectatorInput, SpectatorOutput } from './spectator.js';

/** Short-lived, single-use grants are sent in a WebSocket subprotocol, never a URL. */
export class ConsoleTickets {
  private grants = new Map<string, { vm: string; owner: string; channel: 'display' | 'pointer'; mode: VmConsoleMode; expires: number }>();
  issue(vm: string, owner: string, channel: 'display' | 'pointer' = 'display', mode: VmConsoleMode = 'interactive') {
    for (const [key, grant] of this.grants) if (grant.expires <= Date.now()) this.grants.delete(key);
    if (this.grants.size >= 256) throw new VmError('Too many pending console connections. Try again shortly.', 429);
    const ticket = randomBytes(32).toString('hex');
    this.grants.set(ticket, { vm, owner, channel, mode, expires: Date.now() + 20_000 });
    return ticket;
  }
  consume(vm: string, owner: string, protocols: string | undefined, channel: 'display' | 'pointer' = 'display') {
    const ticket = protocols?.split(',').map((part) => part.trim()).find((part) => /^studio-ticket\.[a-f0-9]{64}$/.test(part))?.slice(14);
    const grant = ticket && this.grants.get(ticket);
    if (!grant || grant.expires <= Date.now() || grant.vm !== vm || grant.owner !== owner || grant.channel !== channel) throw new VmError('Reload the console before reconnecting.', 403);
    this.grants.delete(ticket);
    return grant.mode;
  }
}

/** One RFB byte stream per client; QEMU listens only on its private Unix socket. */
export class ConsoleBridge {
  private peers = new Set<{ id: string; mode: VmConsoleMode; websocket: WebSocket; close: (code?: number, reason?: string) => void }>();
  attach(id: string, websocket: WebSocket, mode: VmConsoleMode = 'interactive') {
    if (this.peers.size >= 32 || [...this.peers].filter((peer) => peer.id === id).length >= 2) {
      websocket.close(1013, 'Too many console connections. Close another console and reconnect.'); return;
    }
    const upstream = createConnection(join(runtimePath(id), 'vnc.sock'));
    const stream = createWebSocketStream(websocket, { highWaterMark: 64 * 1024 });
    const filter = mode === 'spectator' ? new SpectatorInput() : null;
    const output = filter ? new SpectatorOutput(filter) : null;
    let closed = false, alive = true;
    const connectTimer = setTimeout(() => websocket.close(1011, 'The VM display is not ready.'), 5000);
    const heartbeat = setInterval(() => {
      if (!alive || websocket.bufferedAmount > 8 * 1024 * 1024) { peer.close(); return; }
      alive = false; if (websocket.readyState === WebSocket.OPEN) websocket.ping();
    }, 30_000);
    heartbeat.unref();
    const peer = { id, mode, websocket, close: (code?: number, reason = 'Development operation reserved this VM. Reconnect as a spectator.') => {
      if (closed) return; closed = true; clearTimeout(connectTimer); clearInterval(heartbeat);
      stream.unpipe(); filter?.destroy(); output?.destroy(); upstream.destroy(); this.peers.delete(peer);
      if (code && websocket.readyState === WebSocket.OPEN) {
        // Preserve the close code so an open browser can reconnect as a spectator.
        websocket.close(code, reason);
        const timer = setTimeout(() => websocket.terminate(), 1000); timer.unref();
        websocket.once('close', () => { clearTimeout(timer); stream.destroy(); });
      } else { stream.destroy(); websocket.terminate(); }
    } };
    this.peers.add(peer);
    websocket.on('pong', () => { alive = true; });
    websocket.on('close', () => peer.close()); websocket.on('error', () => peer.close());
    stream.on('error', () => peer.close());
    filter?.on('error', () => peer.close(1008, 'Guest input is disabled in spectator mode.'));
    output?.on('error', () => peer.close(1011, 'The private display protocol is not supported.'));
    upstream.on('error', () => { websocket.close(1011, 'The VM display is unavailable. Stop and start the VM if necessary.'); upstream.destroy(); });
    upstream.on('close', () => { if (!closed) { websocket.close(1000, 'VM display disconnected.'); peer.close(); } });
    upstream.on('connect', () => {
      clearTimeout(connectTimer);
      if (filter && output) { upstream.pipe(output).pipe(stream); stream.pipe(filter).pipe(upstream); }
      else { upstream.pipe(stream); stream.pipe(upstream); }
    });
  }
  close() { for (const peer of this.peers) peer.close(); }
  closeVm(id: string) { for (const peer of this.peers) if (peer.id === id) peer.close(); }
  closeControls(id: string) { for (const peer of this.peers) if (peer.id === id && peer.mode === 'interactive') peer.close(4001); }
}
