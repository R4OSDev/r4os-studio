import type { SessionItem } from '../../../../shared/agent-sessions';
import { workflowLabels } from '../project-roadmaps/workflow';
import type { RoadmapWorkflowPhase } from '../../../../shared/project-roadmaps';

export const roadmapLabels: Record<string, string> = {
  'studio.read_roadmap': 'Read roadmap', 'studio.update_roadmap': 'Update roadmap', 'studio.cleanup_roadmap': 'Clean up roadmap',
};
const uuid = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);

export function RoadmapReceipt({ value }: { value: SessionItem['roadmap'] }) {
  if (!value || typeof value !== 'object') return null;
  return <dl className="development-target" aria-label="Roadmap receipt">
    {typeof value.revision === 'number' && Number.isSafeInteger(value.revision) && value.revision > 0 && <div><dt>Roadmap revision</dt><dd>{value.revision}</dd></div>}
    {uuid(value.currentVersionId) && <div><dt>Current version</dt><dd>{value.currentVersionId}</dd></div>}
    {uuid(value.requestId) && <div><dt>Request</dt><dd>{value.requestId}</dd></div>}
    {uuid(value.workflowId) && <div><dt>Cleanup workflow</dt><dd>{value.workflowId}</dd></div>}
    {typeof value.phase === 'string' && Object.hasOwn(workflowLabels, value.phase) && <div><dt>Cleanup status</dt><dd>{workflowLabels[value.phase as RoadmapWorkflowPhase]}</dd></div>}
    {typeof value.code === 'number' && <div><dt>Result</dt><dd>{value.code === 409 ? 'Conflict: read the current roadmap before changing it.' : value.code === 403 ? 'Access denied for this run.' : 'Inspect the original request before retrying.'}</dd></div>}
  </dl>;
}
