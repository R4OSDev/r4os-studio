import type { FastifyInstance } from 'fastify';
import type { SystemPrompt } from '../../../../shared/system-prompt.js';
import { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from '../agent-sessions/host.js';
import { ProjectError, projectStore } from '../projects/store.js';

export async function settingsRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('settings');
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  for (const purpose of ['vision','image-generation'] as const) {
    const base = purpose === 'vision' ? '/fallback' : '/fallback/image-generation';
    app.get(base, async (request, reply) => {
      const session = sessions.session(request, reply, true);
      reply.header('Cache-Control','private, no-store');
      return { ...await agentHost<Record<string, unknown>>({ operation: 'fallback', purpose }), csrfToken: session.token };
    });
    app.get<{Params:{requestId:string}}>(base+'/requests/:requestId', async (request, reply) => {
      sessions.session(request, reply);reply.header('Cache-Control','private, no-store');
      return agentHost({ operation: 'fallback_receipt', purpose, requestId: request.params.requestId });
    });
    app.post(base, { bodyLimit: 4096 }, async (request, reply) => {
      sessions.mutation(request, reply);reply.header('Cache-Control','private, no-store');
      return agentHost({ operation: 'fallback_save', purpose, input: request.body });
    });
  }
  app.get('/context', async (request, reply) => {
    const session=sessions.session(request,reply,true);reply.header('Cache-Control','private, no-store');
    return {...await agentHost<Record<string,unknown>>({operation:'context_settings'}),csrfToken:session.token};
  });
  app.get<{Params:{requestId:string}}>('/context/requests/:requestId', async (request,reply) => {
    sessions.session(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost({operation:'context_settings_receipt',requestId:request.params.requestId});
  });
  app.post('/context',{bodyLimit:4096},async(request,reply) => {
    sessions.mutation(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost({operation:'context_settings_save',input:request.body});
  });
  app.get('/tools' , async (request, reply) => {
    sessions.session(request, reply, true);
    return agentHost({ operation: 'system_tools' });
  });
  const hash = { type: 'string', pattern: '^[a-f0-9]{64}$' };
  const source = { type: 'string', pattern: '^(studio|native|skills|skill-[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12})$' };
  for (const details of [false, true]) {
    app.get<{ Params: { sourceId: string; toolId?: string }; Querystring: { identity: string; after?: string } }>(
      '/tools/:sourceId' + (details ? '/:toolId' : ''), {
        schema: {
          params: { type: 'object', additionalProperties: false, required: details ? ['sourceId','toolId'] : ['sourceId'],
            properties: { sourceId: source, ...(details ? { toolId: hash } : {}) } },
          querystring: { type: 'object', additionalProperties: false, required: ['identity'],
            properties: { identity: hash, ...(details ? {} : { after: { type: 'string', pattern: '^(0|[1-9][0-9]{0,5})$' } }) } },
        },
      }, async (request, reply) => {
        sessions.session(request, reply);
        return agentHost({ operation: 'system_tools', ...request.params, ...request.query });
      });
  }
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
