import { WebSocket } from 'ws';
import type { RawData } from 'ws';
import type { VmPointerInput } from '../../../../shared/virtual-machines.js';
import { qmp } from './qmp.js';
import { setTimeout as delay } from 'node:timers/promises';

const buttons = [[1, 'left'], [2, 'right'], [4, 'middle']] as const;
const released = buttons.map(([, button]) => ({ type: 'btn', data: { button, down: false } }));

/** R4OS currently accepts relative PS/2 motion, not an absolute USB tablet. */
export class PointerControllers {
  private controllers = new Map<string, () => Promise<void>>();
  attach(id: string, socket: WebSocket) {
    if (this.controllers.has(id) || this.controllers.size >= 32) { socket.close(1013, 'Another console is controlling the mouse.'); return; }
    let closed = false, ready = false, held = 0, count = 0, since = Date.now();
    let work: Promise<unknown> = Promise.resolve();
    const queue: VmPointerInput[] = [];
    let draining = false;
    let closing: Promise<void> | undefined, alive = true;
    const heartbeat = setInterval(() => {
      if (!alive) { void close(); return; }
      alive = false; if (socket.readyState === WebSocket.OPEN) socket.ping();
    }, 30_000);
    heartbeat.unref(); socket.on('pong', () => { alive = true; });
    const close = () => {
      if (closing) return closing;
      closed = true; queue.length = 0; clearInterval(heartbeat);
      closing = (async () => {
        await work.catch(() => {});
        // Release after earlier presses have completed, including on transport loss.
        await qmp(id, 'input-send-event', { events: released }).catch(() => {});
        socket.terminate(); this.controllers.delete(id);
      })();
      return closing;
    };
    this.controllers.set(id, close);
    const drain = () => {
      if (draining) return; draining = true;
      work = work.then(async () => {
        while (!closed && queue.length) {
          const next = queue.shift()!;
          let dx = next.dx, dy = next.dy;
          // A PS/2 packet carries at most 127 per axis. Pace larger moves so
          // the guest's i8042 path can consume complete three-byte packets.
          while (!closed && (dx || dy)) {
            const x = Math.max(-96, Math.min(96, dx)), y = Math.max(-96, Math.min(96, dy));
            const events: Record<string, unknown>[] = [];
            if (x) events.push({ type: 'rel', data: { axis: 'x', value: x } });
            if (y) events.push({ type: 'rel', data: { axis: 'y', value: y } });
            await qmp(id, 'input-send-event', { events }); dx -= x; dy -= y;
            if (dx || dy) await delay(8);
          }
          if (closed) break;
          const edges = buttons.filter(([bit]) => (held & bit) !== (next.buttons & bit))
            .map(([bit, button]) => ({ type: 'btn', data: { button, down: Boolean(next.buttons & bit) } }));
          if (edges.length) await qmp(id, 'input-send-event', { events: edges });
          held = next.buttons;
        }
      }).catch(() => { void close(); }).finally(() => { draining = false; });
    };
    socket.on('message', (data: RawData, binary: boolean) => {
      if (closed) return;
      const bytes = Array.isArray(data) ? Buffer.concat(data) : Buffer.from(data as ArrayBuffer);
      if (!ready || binary || bytes.length > 256) { socket.close(1008, 'Invalid mouse input.'); return; }
      if (Date.now() - since >= 1000) { since = Date.now(); count = 0; }
      if (++count > 240) { socket.close(1008, 'Mouse input rate exceeded.'); return; }
      let event: VmPointerInput;
      try { event = JSON.parse(bytes.toString()); } catch { socket.close(1008, 'Invalid mouse input.'); return; }
      if (!event || typeof event !== 'object' || Object.keys(event).sort().join(',') !== 'buttons,dx,dy'
        || !Number.isInteger(event.dx) || Math.abs(event.dx) > 2048 || !Number.isInteger(event.dy) || Math.abs(event.dy) > 2048
        || !Number.isInteger(event.buttons) || event.buttons < 0 || event.buttons > 7) { socket.close(1008, 'Invalid mouse input.'); return; }
      const last = queue.at(-1);
      if (last && last.buttons === event.buttons) {
        last.dx = Math.max(-2048, Math.min(2048, last.dx + event.dx)); last.dy = Math.max(-2048, Math.min(2048, last.dy + event.dy));
      } else queue.push(event);
      if (queue.length > 32) { socket.close(1013, 'Mouse input is delayed.'); return; }
      drain();
    });
    socket.on('close', () => { void close(); }); socket.on('error', () => { void close(); });
    work = qmp(id, 'input-send-event', { events: released }).then(() => {
      if (!closed) { ready = true; socket.send(JSON.stringify({ ready: true })); }
    }).catch(() => { void close(); });
  }
  async close() { await Promise.allSettled([...this.controllers.values()].map((close) => close())); }
}
