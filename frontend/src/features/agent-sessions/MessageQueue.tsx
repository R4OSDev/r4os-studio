import type { useMessageInbox } from './useMessageInbox';

export function MessageQueue({ control }: { control: ReturnType<typeof useMessageInbox> }) {
  const { inbox, posting, pending } = control;
  if (!inbox?.messages.length && !control.error && !pending) return null;
  const waiting = inbox?.messages.filter(value => value.mode === 'queue' && value.state === 'queued') ?? [];
  return <aside className="agent-message-queue" aria-label="Message queue">
    <div className="agent-queue-heading"><strong>{waiting.length} queued</strong>
      {inbox?.held && waiting.length > 0 && <button type="button" disabled={posting || !!pending} onClick={() => void control.perform('resume')}>Continue queue</button>}
      {pending && <button type="button" disabled={posting} onClick={() => void control.perform(pending.action, pending.messageId)}>Retry original queue action</button>}
    </div>
    {inbox?.held && <p role="status">{inbox.reason ?? 'Queue held. Continue explicitly.'}</p>}
    <ol>{inbox?.messages.map(value => <li key={value.requestId}>
      <details><summary>{value.mode === 'steer' ? 'Direct' : '#' + value.sequence} · {value.state} · {value.text.slice(0, 100) || 'Attachments'}</summary>
        <p>{value.text}</p>{value.attachments.length > 0 && <p>{value.attachments.length} attached files</p>}{value.error && <p>{value.error}</p>}</details>
      {value.mode === 'queue' && value.state === 'queued' && <button type="button" aria-label={'Remove queued message ' + value.sequence} disabled={posting || !!pending} onClick={() => void control.perform('cancel', value.requestId)}>Remove</button>}
    </li>)}</ol>
    {control.error && <p role="alert">{control.error}</p>}
  </aside>;
}
