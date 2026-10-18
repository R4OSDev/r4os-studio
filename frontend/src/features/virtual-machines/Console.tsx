import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { VirtualMachine } from '../../../../shared/virtual-machines.js';
import type { VmApi } from './useVms';

function keycode(event: KeyboardEvent) {
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3).toLowerCase();
  if (/^Digit\d$/.test(event.code)) return event.code.slice(5);
  if (/^F(?:[1-9]|1[0-2])$/.test(event.code)) return event.code.toLowerCase();
  return ({ Enter: 'ret', Escape: 'esc', Backspace: 'backspace', Tab: 'tab', Space: 'spc',
    ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Home: 'home', End: 'end',
    Delete: 'delete', PageUp: 'pgup', PageDown: 'pgdn', Minus: 'minus', Equal: 'equal', BracketLeft: 'bracket_left',
    BracketRight: 'bracket_right', Backslash: 'backslash', Semicolon: 'semicolon', Quote: 'apostrophe',
    Comma: 'comma', Period: 'dot', Slash: 'slash', Backquote: 'grave_accent' } as Record<string, string>)[event.code];
}
export function VmConsole({ vm, api }: { vm: VirtualMachine; api: VmApi }) {
  const [screen, setScreen] = useState(''), [error, setError] = useState('');
  const running = ['running', 'paused'].includes(vm.state);
  const queued = useRef(Promise.resolve());
  useEffect(() => {
    if (!running || !api.csrfToken) return;
    let cancelled = false, inFlight = false, previous = '';
    async function frame() {
      if (inFlight || document.hidden) return; inFlight = true;
      try {
        const response = await fetch(`/api/vms/${vm.id}/screen`, { method: 'POST', headers: { 'X-CSRF-Token': api.csrfToken }, cache: 'no-store' });
        if (!response.ok) throw new Error('The display is not ready.');
        const blob = await response.blob();
        if (!cancelled) { const next = URL.createObjectURL(blob); if (previous) URL.revokeObjectURL(previous); previous = next; setScreen(next); setError(''); }
      } catch (cause) { if (!cancelled) setError(cause instanceof Error ? cause.message : 'The display is unavailable.'); }
      finally { inFlight = false; }
    }
    void frame(); const timer = window.setInterval(() => void frame(), 1000);
    return () => { cancelled = true; window.clearInterval(timer); if (previous) URL.revokeObjectURL(previous); };
  }, [vm.id, running, api.csrfToken]);
  function send(event: KeyboardEvent) {
    const key = keycode(event); if (!key || !running) return; event.preventDefault();
    const keys = [...(event.ctrlKey ? ['ctrl'] : []), ...(event.altKey ? ['alt'] : []), ...(event.shiftKey ? ['shift'] : []), key];
    queued.current = queued.current.then(() => api.request<void>(`/${vm.id}/keys`, 'POST', { keys })).catch((cause) => setError(String(cause.message)));
  }
  return <div className="vm-console">
    <p className="vm-help">Click the display to focus keyboard input. The guest uses a US keyboard layout. Display refreshes once per second; mouse control is not included yet.</p>
    {error && <p className="vm-alert" role="status">{error}</p>}
    {!running ? <p>Start the virtual machine to open its console.</p> :
      <div className="vm-screen" tabIndex={0} role="application" aria-label="Virtual machine keyboard console" onKeyDown={send}>
        {screen ? <img src={screen} alt={`${vm.name} display`} /> : <p>Waiting for display…</p>}
      </div>}
    <div className="vm-actions">{['esc', 'ret', 'f1', 'f2', 'f12', 'meta_l'].map((key) => <button type="button" className="button-secondary" disabled={!running}
      key={key} onClick={() => { void api.request(`/${vm.id}/keys`, 'POST', { keys: [key] }).catch((cause) => setError(cause.message)); }}>{key === 'meta_l' ? 'Super' : key === 'ret' ? 'Enter' : key.toUpperCase()}</button>)}</div>
  </div>;
}
