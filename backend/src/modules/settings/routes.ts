import type { FastifyInstance } from 'fastify';
import type { SystemPrompt } from '../../../../shared/system-prompt.js';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError, projectStore } from '../projects/store.js';

export async function settingsRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('settings');
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  for (const [path, helper] of [['system-prompt', 'system_prompt'], ['skill-manager-prompt', 'skill_prompt']] as const) {
    const current = (operation: string, input?: unknown) => projectStore<SystemPrompt>(directory,
      { operation, ...(input === undefined ? {} : { input }) }, helper);

    app.get('/' + path, async (request, reply) => {
      const session = sessions.session(request, reply, true);
      return { ...await current('get'), csrfToken: session.token };
    });
    for (const operation of ['save', 'reset'] as const) {
      app.route<{ Body: { revision: number; text?: string } }>({
        method: operation === 'save' ? 'PATCH' : 'POST',
        url: '/' + path + (operation === 'reset' ? '/reset' : ''),
        bodyLimit: 200 * 1024,
        preValidation: async (request, reply) => {
          sessions.mutation(request, reply);
          const body = request.body;
          const keys = operation === 'save' ? ['revision', 'text'] : ['revision'];
          if (!body || typeof body !== 'object' || Array.isArray(body)
            || Object.keys(body).length !== keys.length || Object.keys(body).some((key) => !keys.includes(key))
            || !Number.isSafeInteger(body.revision) || body.revision < 0
            || (operation === 'save' && typeof body.text !== 'string')) {
            throw new ProjectError('Invalid prompt settings.', 400);
          }
        },
        handler: async (request, reply) => ({ ...await current(operation, request.body), csrfToken: sessions.session(request, reply).token }),
      });
    }
  }
}
