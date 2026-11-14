export function parseRoadmapRoute(hash: string) {
  const match = /^#projects\/([a-f0-9-]{36})\/roadmap(?:\/versions\/([a-f0-9-]{36})(?:\/subversions\/([a-f0-9-]{36}))?)?$/.exec(hash);
  return match ? { projectId: match[1], versionId: match[2], subversionId: match[3] } : null;
}
export function roadmapHash(projectId: string, versionId?: string, subversionId?: string) {
  return `#projects/${projectId}/roadmap${versionId ? '/versions/' + versionId + (subversionId ? '/subversions/' + subversionId : '') : ''}`;
}
