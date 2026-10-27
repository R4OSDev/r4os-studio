import type { RoadmapItemStatus, RoadmapVersionStatus } from '../../../../shared/project-roadmaps';

// Versions and work items deliberately use different completion vocabularies.
export const versionStatusLabels: Record<RoadmapVersionStatus, string> = {
  open: 'Open', complete: 'Complete', discarded: 'Discarded',
};
export const itemStatusLabels: Record<RoadmapItemStatus, string> = {
  open: 'Open', done: 'Done', discarded: 'Discarded',
};
