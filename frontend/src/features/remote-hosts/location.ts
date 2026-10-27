const root = '#system/remote-hosts';
export function parseRemoteHostRoute(hash: string): { id: string | null; view: 'Overview' | 'Settings' } | null {
  if (hash === root) return { id: null, view: 'Overview' };
  const value = /^#system\/remote-hosts\/([a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12})(?:\/(overview|settings))?$/.exec(hash);
  return value ? { id: value[1], view: value[2] === 'settings' ? 'Settings' : 'Overview' } : null;
}
export const remoteHostHash = (id: string | null, view = 'Overview') => id ? `${root}/${id}/${view.toLowerCase()}` : root;
