export function environmentNoteRequestKey(scope: 'project' | 'skill', ownerId: string, sessionId: string) {
  return `studio.environment-notes.delete.${scope}.${ownerId}.${sessionId}`;
}
export function clearEnvironmentNoteRequests(scope: 'project' | 'skill', ownerId: string) {
  const prefix = `studio.environment-notes.delete.${scope}.${ownerId}.`;
  try {
    for (let index = localStorage.length - 1; index >= 0; index--) {
      const key = localStorage.key(index); if (key?.startsWith(prefix)) localStorage.removeItem(key);
    }
  } catch { /* Confirmed owner deletion must still finish if browser storage is unavailable. */ }
}
