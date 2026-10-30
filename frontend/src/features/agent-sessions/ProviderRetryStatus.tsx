import { useEffect, useState } from 'react';
import type { AgentRun, ProviderRetry } from '../../../../shared/agent-sessions';

export function ProviderRetryStatus({ run }: { run: AgentRun | null | undefined }) {
  const retry = run?.providerRetry;
  if (!retry || retry.state === 'completed') return null;
  return <RetryStatus key={`${run?.id}:${retry.sequence}:${retry.attempt}:${retry.state}:${retry.sampledAt}`} retry={retry}/>;
}

function RetryStatus({ retry }: { retry: ProviderRetry }) {
  const [started] = useState(() => performance.now());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (retry.state !== 'waiting') return;
    const timer = window.setInterval(() => setElapsed(performance.now() - started), 250);
    return () => window.clearInterval(timer);
  }, [retry.state, started]);
  const remaining = Math.ceil(Math.max(0, retry.remainingMs - elapsed) / 1000);
  let detail: string;
  if (retry.state === 'waiting') detail = remaining > 0
    ? `Next attempt ${retry.nextAttempt}/${retry.maxAttempts} in ${remaining}s.`
    : `Checking original admission for attempt ${retry.nextAttempt}/${retry.maxAttempts}…`;
  else if (retry.state === 'submitting') detail = `Starting attempt ${retry.attempt}/${retry.maxAttempts}…`;
  else if (retry.state === 'continuing') detail = `Continuing · attempt ${retry.attempt}/${retry.maxAttempts}.`;
  else if (retry.state === 'exhausted') detail = 'Automatic continuation stopped after five attempts. Send or Play explicitly to continue.';
  else if (retry.state === 'unknown') detail = 'The original continuation is unconfirmed. Review its retained result before continuing.';
  else detail = 'Automatic continuation ended. Review the original run before continuing.';
  return <div className="agent-provider-retry" role="status" aria-live="polite">
    <span>{retry.error}</span><span aria-live="off">{detail}</span>
  </div>;
}
