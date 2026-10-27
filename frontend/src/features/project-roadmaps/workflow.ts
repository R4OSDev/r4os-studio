import type { RoadmapWorkflowPhase } from '../../../../shared/project-roadmaps';

export const workflowLabels: Record<RoadmapWorkflowPhase, string> = {
  preparing: 'Preparing archive', archiving: 'Writing archive', archive_ready: 'Archive verified',
  documents_verified: 'Documents verified', complete: 'Complete', cancelled: 'Cancelled', aborted: 'Aborted',
};
