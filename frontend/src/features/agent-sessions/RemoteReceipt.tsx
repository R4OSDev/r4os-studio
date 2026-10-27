import type { RemoteReceiptSummary } from '../../../../shared/agent-sessions';

export function RemoteReceipt({ value }: { value: RemoteReceiptSummary }) {
  const name = typeof value.hostName === 'string' ? value.hostName.slice(0, 200) : '';
  const id = typeof value.id === 'string' && /^[a-f0-9-]{36}$/.test(value.id) ? value.id : '';
  return <div aria-label="Remote Host receipt">
    <dl className="development-target">
      {name && <div><dt>Remote Host</dt><dd>{name}</dd></div>}
      {id && <div><dt>Original job</dt><dd>{id}</dd></div>}
      {typeof value.state === 'string' && <div><dt>Job status</dt><dd>{value.state.slice(0, 40)}</dd></div>}
      {typeof value.phase === 'string' && <div><dt>Phase</dt><dd>{value.phase.slice(0, 80)}</dd></div>}
      {typeof value.requestId === 'string' && <div><dt>Request</dt><dd>{value.requestId.slice(0, 36)}</dd></div>}
    </dl>
    {value.stopRequested === true && <p>Local cancellation requested.</p>}
    {value.localClientEndConfirmed === true && <p>Local SSH client ended.</p>}
    {value.remoteProcessEndConfirmed === false && <p>Remote process end remains unconfirmed.</p>}
    {value.state === 'unknown' && <p>The original result is unconfirmed. Inspect this job before further changes.</p>}
  </div>;
}
