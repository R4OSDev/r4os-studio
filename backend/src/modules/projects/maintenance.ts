import { existsSync } from 'node:fs';
import { agentHost } from '../agent-sessions/host.js';
import { developmentHost } from '../project-development/host.js';

export async function maintenanceHosts() {
  const supports = async (read: () => Promise<{ enabled: boolean; projectDeletionLocks?: number }>, socket: string) => {
    try {
      const status = await read(), ready = status.enabled && status.projectDeletionLocks === 1;
      return { ready, unsafe: !ready };
    } catch { return { ready: false, unsafe: existsSync(socket) }; }
  };
  const [agents, development] = await Promise.all([
    supports(() => agentHost({ operation: 'capabilities' }), process.env.STUDIO_AGENTS_SOCKET ?? '/run/r4os-studio-agents/host.sock'),
    supports(() => developmentHost({ operation: 'capabilities' }), process.env.STUDIO_DEVELOPMENT_SOCKET ?? '/run/r4os-studio-development/host.sock'),
  ]);
  return { agents: agents.ready, development: development.ready, unsafe: agents.unsafe || development.unsafe };
}
