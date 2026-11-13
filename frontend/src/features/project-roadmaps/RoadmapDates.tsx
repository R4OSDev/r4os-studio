import type { RoadmapVersionStatus } from '../../../../shared/project-roadmaps';

const dateTime = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' });

function Timestamp({ value }: { value: string | null | undefined }) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : <time dateTime={value}>{dateTime.format(date)}</time>;
}

export function RoadmapDates({ entry }: { entry: { createdAt: string; completedAt?: string | null; status?: RoadmapVersionStatus } }) {
  return <dl className="roadmap-dates">
    <div><dt>Created</dt><dd><Timestamp value={entry.createdAt} /></dd></div>
    {entry.status === 'complete' && <div><dt>Completed</dt><dd><Timestamp value={entry.completedAt} /></dd></div>}
  </dl>;
}
