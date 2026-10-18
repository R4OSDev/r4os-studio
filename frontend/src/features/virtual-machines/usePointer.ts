import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { VmPointerInput } from '../../../../shared/virtual-machines.js';
import { vmRequest } from './api';

/** Pointer lock avoids inventing absolute tablet support in the R4OS guest. */
export function usePointer(id: string, token: string, enabled: boolean, target: RefObject<HTMLDivElement | null>) {
  const [captured, setCaptured] = useState(false), [ready, setReady] = useState(false), [error, setError] = useState('');
  const captureAction = useRef<() => void>(() => {});
  useEffect(() => {
    const element = target.current;
    if (!element || !enabled) return;
    let socket: WebSocket | null = null, locked = false, connected = false, generation = 0;
    let timer: number | undefined;
    let pending: VmPointerInput = { dx: 0, dy: 0, buttons: 0 };
    const clamp = (value: number) => Math.max(-2048, Math.min(2048, value));
    function flush(force = false) {
      if (!connected || !socket || socket.readyState !== WebSocket.OPEN || (!force && !pending.dx && !pending.dy)) return;
      if (socket.bufferedAmount > 64 * 1024) { document.exitPointerLock(); setError('Mouse input is delayed. Capture the mouse again.'); return; }
      socket.send(JSON.stringify(pending)); pending = { dx: 0, dy: 0, buttons: pending.buttons };
    }
    function release() {
      generation++; locked = false; connected = false;
      window.clearInterval(timer); timer = undefined;
      const previous = socket; socket = null; previous?.close();
      pending = { dx: 0, dy: 0, buttons: 0 }; setCaptured(false); setReady(false);
    }
    async function connect() {
      const current = ++generation;
      try {
        const { ticket } = await vmRequest<{ ticket: string }>(`/${id}/pointer-ticket`, token, 'POST');
        if (!locked || generation !== current) return;
        const url = new URL(`/api/vms/${id}/pointer`, window.location.href); url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const channel = new WebSocket(url, ['studio-input', `studio-ticket.${ticket}`]); socket = channel;
        channel.onmessage = (event) => {
          if (socket !== channel) return;
          try { if (JSON.parse(event.data).ready === true) { connected = true; setReady(true); timer = window.setInterval(() => flush(), 33); } }
          catch { document.exitPointerLock(); setError('The mouse connection was interrupted.'); }
        };
        channel.onerror = () => { if (socket === channel) setError('Mouse control is unavailable. Capture the mouse again.'); };
        channel.onclose = (event) => {
          if (socket !== channel) return;
          document.exitPointerLock(); release(); setError(event.reason || 'Mouse control disconnected. Capture the mouse again.');
        };
      } catch (cause) {
        if (generation === current) { document.exitPointerLock(); release(); setError(cause instanceof Error ? cause.message : 'Mouse control is unavailable.'); }
      }
    }
    function capture() {
      const canvas = element!.querySelector('canvas');
      if (!canvas) return;
      setError(''); canvas.focus();
      // This must run directly inside a user gesture, before fetching a ticket.
      try { const request = canvas.requestPointerLock(); if (request) void request.catch(() => setError('Mouse capture is unavailable. Allow pointer lock in the browser.')); }
      catch { setError('Mouse capture is unavailable in this browser.'); }
    }
    captureAction.current = capture;
    function changed() {
      const canvas = element!.querySelector('canvas');
      const active = Boolean(canvas && document.pointerLockElement === canvas);
      if (active && !locked) { locked = true; setCaptured(true); void connect(); }
      else if (!active && locked) release();
    }
    function blocked() { setError('Mouse capture was blocked. Allow pointer lock in the browser.'); }
    function mouse(event: MouseEvent) {
      const canvas = element!.querySelector('canvas');
      if (!canvas || (event.target !== canvas && document.pointerLockElement !== canvas)) return;
      event.stopImmediatePropagation(); event.preventDefault();
      if (event.type === 'mousedown' && !locked) { if (event.button === 0) capture(); return; }
      if (!locked) return;
      if (event.type === 'mousemove') {
        const canvas = element!.querySelector('canvas')!;
        const ratio = canvas.width / Math.max(1, canvas.getBoundingClientRect().width);
        pending.dx = clamp(pending.dx + Math.round(event.movementX * ratio)); pending.dy = clamp(pending.dy + Math.round(event.movementY * ratio));
      } else if (event.type === 'mousedown' || event.type === 'mouseup') { pending.buttons = event.buttons & 7; flush(true); }
    }
    function touch(event: TouchEvent) { event.stopImmediatePropagation(); event.preventDefault(); setError('This guest needs a captured mouse. Use a desktop browser, or enable View only.'); }
    function blurred() { if (locked) document.exitPointerLock(); }
    function wheel(event: WheelEvent) { event.stopImmediatePropagation(); if (locked) event.preventDefault(); }
    const mouseEvents = ['mousemove', 'mousedown', 'mouseup', 'contextmenu'] as const;
    for (const name of mouseEvents) element.addEventListener(name, mouse, true);
    element.addEventListener('wheel', wheel, { capture: true, passive: false });
    const touchEvents = ['touchstart', 'touchmove', 'touchend'] as const;
    for (const name of touchEvents) element.addEventListener(name, touch, { capture: true, passive: false });
    window.addEventListener('blur', blurred);
    document.addEventListener('pointerlockchange', changed); document.addEventListener('pointerlockerror', blocked);
    return () => {
      captureAction.current = () => {};
      if (locked) document.exitPointerLock(); release();
      for (const name of mouseEvents) element.removeEventListener(name, mouse, true);
      element.removeEventListener('wheel', wheel, true);
      for (const name of touchEvents) element.removeEventListener(name, touch, true);
      window.removeEventListener('blur', blurred);
      document.removeEventListener('pointerlockchange', changed); document.removeEventListener('pointerlockerror', blocked);
    };
  }, [id, token, enabled, target]);
  return { captured, ready, error, capture: () => captureAction.current(), release: () => document.exitPointerLock() };
}
