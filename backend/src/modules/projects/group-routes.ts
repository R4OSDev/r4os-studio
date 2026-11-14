import type { FastifyInstance } from 'fastify';
import type { ProjectGrouping } from '../../../../shared/projects.js';
import type { ProjectSessions } from './sessions.js';
import { projectStore } from './store.js';

export function projectGroupRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  const changes = [
    { method: 'POST', url: '/groups/:id', operation: 'create_group' },
    { method: 'PATCH', url: '/groups/:id', operation: 'rename_group' },
    { method: 'DELETE', url: '/groups/:id', operation: 'delete_group' },
    { method: 'PUT', url: '/:id/group', operation: 'move_project' },
  ] as const;

  for (const { method, url, operation } of changes) {
    app.route<{ Params: { id: string }; Body: unknown }>({
      method, url, bodyLimit: 4096,
      handler: async (request, reply) => {
        sessions.mutation(request, reply);
        return projectStore<ProjectGrouping>(directory, { operation, id: request.params.id, input: request.body });
      },
    });
  }
}
