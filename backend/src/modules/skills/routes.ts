import type { FastifyInstance } from 'fastify';
import type { Skill, SkillDetail, SkillFileContent, SkillValidation } from '../../../../shared/skills.js';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { skillStore } from './store.js';

function body(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProjectError('Invalid skill request.', 400);
  return value as Record<string, unknown>;
}
export async function skillRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('skills');
  app.setErrorHandler((cause, _request, reply) => {
    const error = cause instanceof ProjectError ? cause : new ProjectError('The skill request could not be completed.', 400);
    void reply.code(error.statusCode).send({ message: error.message });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
  });
  app.get('/', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    return { skills: await skillStore<Skill[]>(directory, { operation: 'list' }), csrfToken: session.token };
  });
  app.post('/', { bodyLimit: 4096 }, async (request) => skillStore<SkillDetail>(directory, { operation: 'create', input: body(request.body) }));
  app.patch<{ Params: { id: string } }>('/:id', { bodyLimit: 4096 }, async (request) => {
    const input = body(request.body); if (Object.hasOwn(input, 'id')) throw new ProjectError('Unexpected skill fields.', 400);
    return skillStore<SkillDetail>(directory, { operation: 'rename', input: { ...input, id: request.params.id } });
  });
  app.get<{ Params: { id: string } }>('/:id', async (request, reply) => {
    sessions.session(request, reply); return skillStore<SkillDetail>(directory, { operation: 'get', id: request.params.id });
  });
  app.get<{ Params: { id: string }; Querystring: { path: string } }>('/:id/file', async (request, reply) => {
    sessions.session(request, reply); return skillStore<SkillFileContent>(directory, { operation: 'read', id: request.params.id, path: request.query.path });
  });
  app.put<{ Params: { id: string } }>('/:id/file', { bodyLimit: 8 * 1024 * 1024 }, async (request) => {
    const input = body(request.body); if (Object.hasOwn(input, 'id')) throw new ProjectError('Unexpected skill fields.', 400);
    return skillStore<SkillDetail>(directory, { operation: 'write', input: { ...input, id: request.params.id } });
  });
  for (const [method, suffix, operation] of [['DELETE', '/file', 'remove_file'], ['POST', '/file/rename', 'rename_file']] as const) {
    app.route<{ Params: { id: string } }>({ method, url: '/:id' + suffix, bodyLimit: 4096,
      handler: async (request) => {
        const input = body(request.body); if (Object.hasOwn(input, 'id')) throw new ProjectError('Unexpected skill fields.', 400);
        return skillStore<SkillDetail>(directory, { operation, input: { ...input, id: request.params.id } });
      },
    });
  }
  app.post<{ Params: { id: string } }>('/:id/validate', { bodyLimit: 4096 }, async (request) => {
    if (request.body !== undefined && Object.keys(body(request.body)).length) throw new ProjectError('Unexpected validation fields.', 400);
    return skillStore<SkillValidation>(directory, { operation: 'validate', id: request.params.id });
  });
  app.post<{ Params: { id: string } }>('/:id/save', { bodyLimit: 4096 }, async (request) => {
    const input = body(request.body); if (Object.hasOwn(input, 'id')) throw new ProjectError('Unexpected skill fields.', 400);
    return skillStore<SkillDetail & { saved: boolean; validation: SkillValidation }>(directory, { operation: 'save', input: { ...input, id: request.params.id } });
  });
}
