import type { FastifyInstance } from 'fastify';
import type { ProjectsResponse } from '../../../../shared/projects.js';
import { listProjects, projectStore } from './store.js';
import { ProjectSessions } from './sessions.js';

export async function projectRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  app.get('/options', async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'options' }, 'sdk');
  });

  app.get<{ Reply: ProjectsResponse | { message: string } }>('/', async (request, reply) => {
    try { return { projects: await listProjects(directory), csrfToken: sessions.session(request, reply, true).token }; }
    catch (error) {
      app.log.error(error, 'Project inventory could not be read.');
      return reply.code(503).send({ message: 'Projects could not be loaded.' });
    }
  });
}
