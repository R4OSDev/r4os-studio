import { useEffect, useRef, useState } from 'react';
import type RFB from '@novnc/novnc';
import type { VirtualMachine } from '../../../../shared/virtual-machines.js';
import type { VmApi } from './useVms';
import { vmRequest } from './api';
import { usePointer } from './usePointer';

const shortcuts = [
  { label: 'Esc', keys: ['esc'] },
  { label: 'Enter', keys: ['ret'] },
  { label: 'Super', keys: ['meta_l'] },
  { label: 'Alt+Tab', keys: ['alt', 'tab'] },
  { label: 'Ctrl+C', keys: ['ctrl', 'c'] },
] as const;

export function VmConsole({ vm, api }: { vm: VirtualMachine; api: VmApi }) {
  const container = useRef<HTMLDivElement>(null), display = useRef<HTMLDivElement>(null);
  const client = useRef<RFB | null>(null);
  const [status, setStatus] = useState('Connecting'), [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0), [fit, setFit] = useState(true), [viewOnly, setViewOnly] = useState(false);
  const [fullscreen, setFullscreen] = useState(false), [focused, setFocused] = useState(false);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const running = ['running', 'paused'].includes(vm.state);
  const pointer = usePointer(vm.id, api.csrfToken, running && status === 'Connected' && !viewOnly, display);
  const preferences = useRef({ fit, viewOnly });
  useEffect(() => {
    preferences.current = { fit, viewOnly };
    if (client.current) { client.current.scaleViewport = fit; client.current.viewOnly = viewOnly; }
  }, [fit, viewOnly]);

  useEffect(() => {
    if (!running || !api.csrfToken || !display.current) return;
    const target = display.current;
    let cancelled = false, rfb: RFB | null = null;
    const observer = new MutationObserver(() => {
      const canvas = target.querySelector('canvas');
      if (canvas) setSize((old) => old.width === canvas.width && old.height === canvas.height ? old : { width: canvas.width, height: canvas.height });
    });
    observer.observe(target, { subtree: true, childList: true, attributes: true, attributeFilter: ['width', 'height'] });
    async function connect() {
      // Load the decoder only when a running VM console is opened.
      const { default: RemoteFrameBuffer } = await import('@novnc/novnc');
      if (cancelled) return;
      setStatus('Connecting'); setError(''); setSize({ width: 0, height: 0 });
      const { ticket } = await vmRequest<{ ticket: string }>(`/${vm.id}/console-ticket`, api.csrfToken, 'POST');
      if (cancelled) return;
      const url = new URL(`/api/vms/${vm.id}/console`, window.location.href);
      url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      rfb = new RemoteFrameBuffer(target, url.href, { shared: true, wsProtocols: ['binary', `studio-ticket.${ticket}`] });
      client.current = rfb;
      rfb.scaleViewport = preferences.current.fit; rfb.viewOnly = preferences.current.viewOnly;
      rfb.resizeSession = false; rfb.clipViewport = false; rfb.focusOnClick = true;
      rfb.background = '#100c16'; rfb.qualityLevel = 9; rfb.compressionLevel = 2;
      rfb.addEventListener('connect', () => { if (!cancelled) { setStatus('Connected'); setError(''); } });
      rfb.addEventListener('disconnect', () => {
        if (!cancelled) { setStatus('Disconnected'); setFocused(false); setError('The display connection closed. Reconnect to continue.'); }
      });
      rfb.addEventListener('securityfailure', () => { if (!cancelled) setError('The display connection was rejected. Reconnect to request a new session.'); });
    }
    void connect().catch((cause: unknown) => {
      if (!cancelled) { setStatus('Disconnected'); setError(cause instanceof Error ? cause.message : 'The display is unavailable.'); }
    });
    return () => { cancelled = true; observer.disconnect(); rfb?.disconnect(); if (client.current === rfb) client.current = null; };
  }, [vm.id, running, api.csrfToken, attempt]);

  useEffect(() => {
    function changed() { setFullscreen(document.fullscreenElement === container.current); }
    function escape(event: KeyboardEvent) {
      if (event.code !== 'Escape' || (document.fullscreenElement !== container.current && !container.current?.contains(document.pointerLockElement))) return;
      event.preventDefault(); event.stopImmediatePropagation(); document.exitPointerLock();
      if (document.fullscreenElement === container.current) void document.exitFullscreen().catch(() => {});
    }
    document.addEventListener('fullscreenchange', changed); document.addEventListener('keydown', escape, true);
    return () => { document.removeEventListener('fullscreenchange', changed); document.removeEventListener('keydown', escape, true); };
  }, []);
  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement === container.current) await document.exitFullscreen();
      else await container.current?.requestFullscreen();
    } catch { setError('Fullscreen is unavailable in this browser.'); }
  }
  function shortcut(keys: readonly string[]) {
    if (!client.current || viewOnly || status !== 'Connected') return;
    // The guest needs a held chord for modifier shortcuts; use the existing
    // QMP key action instead of releasing all keys in the same browser tick.
    void vmRequest<void>(`/${vm.id}/keys`, api.csrfToken, 'POST', { keys })
      .then(() => client.current?.focus()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'The shortcut could not be sent.'));
  }
  function screenshot() {
    client.current?.toBlob((blob) => {
      if (!blob) { setError('No display frame is available yet.'); return; }
      const url = URL.createObjectURL(blob), anchor = document.createElement('a');
      anchor.href = url; anchor.download = `r4os-${vm.id}-${new Date().toISOString().replaceAll(':', '-')}.png`;
      anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, 'image/png');
  }
  const connected = running && status === 'Connected';
  return <div className="vm-console" ref={container}>
    <div className="vm-console-toolbar">
      {size.width > 0 && running && <span className="vm-console-resolution">{size.width} × {size.height}</span>}
      <div className="vm-console-tools">
        <button className="button-secondary" aria-pressed={fit} onClick={() => setFit(true)}>Fit to window</button>
        <button className="button-secondary" aria-pressed={!fit} onClick={() => setFit(false)}>Actual size</button>
        <button className="button-secondary" aria-pressed={viewOnly} onClick={() => setViewOnly(!viewOnly)}>View only</button>
        <button className="button-secondary" disabled={!connected || viewOnly} onClick={() => pointer.captured ? pointer.release() : pointer.capture()}>{pointer.captured ? 'Release mouse' : 'Capture mouse'}</button>
        <button className="button-secondary" disabled={!connected} onClick={screenshot}>Screenshot</button>
        <button className="button-secondary" disabled={!running} onClick={() => setAttempt((value) => value + 1)}>Reconnect</button>
        <button className="button-secondary" disabled={!document.fullscreenEnabled || (!running && !fullscreen)} onClick={() => void toggleFullscreen()}>{fullscreen ? 'Exit fullscreen' : 'Fullscreen'}</button>
      </div>
    </div>
    {(error || pointer.error) && <p className="vm-alert" role="status">{error || pointer.error}</p>}
    <div className={`vm-console-stage ${!running ? 'powered-off' : ''}`}>
      <div className="vm-console-display" ref={display} role="application" aria-label={`${vm.name} remote display`}
        onFocusCapture={() => setFocused(true)} onBlurCapture={() => setFocused(false)} />
      {!running && <p className="vm-console-placeholder">Start the virtual machine to open its console.</p>}
      {running && status === 'Connecting' && <p className="vm-console-placeholder">Connecting to display…</p>}
    </div>
    <div className="vm-console-bottom">
      <div className="vm-console-shortcuts" aria-label="Guest keyboard shortcuts">{shortcuts.map(({ label, keys }) => <button type="button" key={label} className="button-secondary" disabled={!connected || viewOnly} onClick={() => shortcut(keys)}>{label}</button>)}</div>
      <p className="vm-help">{viewOnly ? 'View only: input is disabled.' : pointer.captured ? pointer.ready ? 'Mouse captured. Keyboard and mouse control the guest.' : 'Connecting mouse…' : focused && connected ? 'Keyboard focused. Click the display to capture the mouse.' : 'Click the display to capture the mouse and focus the keyboard.'} Escape releases the mouse and exits fullscreen.</p>
    </div>
  </div>;
}
