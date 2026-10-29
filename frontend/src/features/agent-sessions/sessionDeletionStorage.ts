import type { SessionDeletionInput } from '../../../../shared/agent-sessions';
export const deletionKey = (scope: string, owner: string, sid: string) => `studio.session.deletion.${scope}.${owner}.${sid}`;
export function pendingDeletion(scope: string, owner: string, sid: string): SessionDeletionInput | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(deletionKey(scope, owner, sid)) ?? 'null');
    return value?.requestId && value?.scopeHash && typeof value.confirmName === 'string' ? value : null;
  } catch { return null; }
}
export function clearDeletedSession(scope: string, owner: string, sid: string, creationIds: string[] = []) {
  const exact = [deletionKey(scope, owner, sid), `studio.goal.${scope}.${owner}.${sid}`, `studio.attachments.${scope}.${owner}.${sid}`,
    `studio.${scope}.queue-control.${sid}`, ...(scope === 'skill' ? [`studio.skill.session.run.${sid}`, `studio.skill.session.draft.${sid}`] : [`studio.session.run.${sid}`, `studio.session.draft.${sid}`])];
  for (const storage of [sessionStorage, localStorage]) {
    for (let i = storage.length - 1; i >= 0; i--) {
      const key = storage.key(i);
      if (key && (exact.some(value => key === value || key.startsWith(value + '.')) || key === `studio.environment-notes.delete.${scope}.${owner}.${sid}`)) storage.removeItem(key);
    }
    const createKey = (scope === 'skill' ? 'studio.skill.session.create.' : 'studio.session.create.') + owner;
    try { const value = JSON.parse(storage.getItem(createKey) ?? 'null'); if (creationIds.includes(value?.requestId) || value?.session?.id === sid || value?.sessionId === sid) storage.removeItem(createKey); } catch { /* Preserve another unconfirmed creation. */ }
  }
}
export function announceDeletedSession(scope: string, owner: string, sid: string) {
  try { const channel = new BroadcastChannel('studio-session-lifetimes'); channel.postMessage({ scope, owner, sid, deleted: true }); channel.close(); } catch { /* Confirmed HTTP deletion still succeeds. */ }
}
