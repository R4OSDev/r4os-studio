import { useEffect, useId, useState } from 'react';
import type { RemoteHost } from '../../../../shared/remote-hosts';
import { listHosts } from './api';

export function HostSelect({ value, changed, disabled = false }: { value: string; changed: (id: string) => void; disabled?: boolean }) {
  const id = useId(); const [hosts, setHosts] = useState<RemoteHost[]>([]), [error, setError] = useState(''), [ready, setReady] = useState(false), [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listHosts(controller.signal).then((result) => { if (!controller.signal.aborted) { setHosts(result.hosts); setReady(true); setError(''); } })
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [epoch]);
  const host = hosts.find((h) => h.id === value);
  return <div className="project-field"><label htmlFor={id}>Remote host</label>
    <select id={id} value={value} disabled={disabled || (!ready && !error)} onChange={(event) => changed(event.target.value)}>
      <option value="">None</option>{value && !host && <option value={value}>{ready ? 'Missing Remote Host' : 'Current Remote Host'} ({value})</option>}
      {hosts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    {host && <p className="project-message">{host.name} · {host.address}:{host.port} · {host.lastTest?.status === 'success' ? 'Previously confirmed' : host.lastTest ? 'Connection not confirmed' : 'Not tested'}</p>}
    {ready && value && !host && <p className="project-error" role="status">This project’s saved host is missing. Select None or an available local host.</p>}
    {error && <><p className="project-error" role="alert">Remote Hosts could not be loaded. {error}</p><button type="button" disabled={disabled} onClick={() => setEpoch((n) => n + 1)}>Reload Remote Hosts</button></>}
    <p className="project-message">Optional, in addition to the VM. Available for explicit tasks; assigning a host does not connect or change the VM target.</p>
  </div>;
}
