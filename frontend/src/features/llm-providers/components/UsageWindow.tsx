import type { UsageWindow as Window } from '../../../../../shared/llm-providers.js';
import { dateTime, duration, percent, untilReset } from '../usage-format';

export function UsageWindow({ window, label, bucket, now }: { window: Window; label: string; bucket: string; now: number }) {
  const title = duration(window.windowDurationMins, label);
  return <div className="usage-window">
    <div className="usage-window-heading"><h5>{title}</h5><strong>{percent(window.remainingPercent)}{window.remainingPercent !== null && ' remaining'}</strong></div>
    {window.usedPercent !== null && <progress max={100} value={Math.min(100, window.usedPercent)} aria-label={`${bucket} ${title} usage`} />}
    <p>{percent(window.usedPercent)}{window.usedPercent !== null && ' used'}</p>
    <p className="usage-reset-time">{untilReset(window.resetsAt, now)}</p>
    {window.resetsAt && <time dateTime={window.resetsAt}>{dateTime(window.resetsAt)}</time>}
  </div>;
}
