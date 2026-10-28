const identity = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
export function parseBoardRoute(hash: string) {
  const match = new RegExp(`^#projects/(${identity})/boards(?:/(${identity}))?$`).exec(hash);
  return match ? { projectId: match[1], boardId: match[2] } : null;
}
export function boardHash(projectId: string, boardId?: string) { return `#projects/${projectId}/boards${boardId ? '/' + boardId : ''}`; }
