import {useEffect, useState} from 'react';
import type {ContextCompaction} from '../../../../shared/agent-sessions';

const format = new Intl.NumberFormat('en-US');

export function CompactionProgress({progress}: {progress: ContextCompaction}) {
  const running = progress.state === 'running';
  const [time, setTime] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const interval = window.setInterval(() => setTime(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [running]);
  const elapsed = running ? Math.max(progress.elapsedMs, time - Date.parse(progress.startedAt)) : progress.elapsedMs;
  const title = running ? 'Summarizing context' : progress.state === 'completed' ? 'Context reduced' : 'Compaction stopped';
  return <section className="context-compaction-progress" aria-label="Context compaction">
    <strong role="status">{title}</strong>
    <dl className="context-facts">
      <dt>Completed steps</dt><dd>{progress.completedSteps} / {progress.maximumSteps}</dd>
      <dt>Elapsed</dt><dd>{format.format(Math.floor(elapsed / 1000))} s</dd>
      <dt>Estimated input</dt><dd>{format.format(progress.before.estimatedTokens)}{progress.after && ' → ' + format.format(progress.after.estimatedTokens)} tokens</dd>
      <dt>Images</dt><dd>{format.format(progress.before.images)}{progress.after && ' → ' + format.format(progress.after.images)}</dd>
      {progress.targetTokens != null && <><dt>Compaction target</dt><dd>{format.format(progress.targetTokens)} tokens</dd></>}
    </dl>
    {progress.reason && <p>{progress.reason}</p>}
  </section>;
}
