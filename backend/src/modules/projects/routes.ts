import type { FastifyInstance } from 'fastify';
import type { Project, ProjectInput, ProjectOptions, ProjectUpdate, ProjectsResponse } from '../../../../shared/projects.js';
import { listProjects, projectStore, ProjectError } from './store.js';
import { ProjectSessions } from './sessions.js';
import { agentSessionRoutes } from '../agent-sessions/routes.js';
import { runRoutes } from '../agent-sessions/run-routes.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = {
  name: { type: 'string', minLength: 1, maxLength: 120 },
  description: { type: 'string', maxLength: 4000 },
  vmId: { anyOf: [identity, { type: 'null' }] },
};
function controlCharacters(value: string, allowed: number[] = []) {
  return Array.from(value).some((character) => {
    const code = character.codePointAt(0)!;
    return code === 127 || (code < 32 && !allowed.includes(code));
  });
}

function validateFields(value: unknown, allowed: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).some((key) => !allowed.includes(key))) throw new ProjectError('Unexpected project fields.', 400);
  const body = value as Record<string, unknown>;
  for (const key of ['name', 'description', 'language', 'template', 'optionsRevision', 'requestId']) {
    if (Object.hasOwn(body, key) && typeof body[key] !== 'string') throw new ProjectError('Invalid project input.', 400);
  }
  if (typeof body.name === 'string') {
    const name = body.name.trim();
    if (!name || controlCharacters(name)) throw new ProjectError('Enter a valid project name.', 400);
    body.name = name;
  }
  if (typeof body.description === 'string' && controlCharacters(body.description, [9, 10, 13])) {
    throw new ProjectError('Description contains invalid characters.', 400);
  }
  if (Object.hasOwn(body, 'revision') && !Number.isSafeInteger(body.revision)) throw new ProjectError('Invalid project revision.', 400);
  if (Object.hasOwn(body, 'vmId') && body.vmId !== null && typeof body.vmId !== 'string') throw new ProjectError('Invalid virtual machine.', 400);
}

export async function projectRoutes(app: FastifyInstance, { directory, providerDirectory }: { directory: string; providerDirectory?: string }) {
  const sessions = new ProjectSessions();
  agentSessionRoutes(app, directory, sessions, providerDirectory);
  runRoutes(app, sessions);
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  app.addHook('onReady', async () => {
    void projectStore<{ id: string; recovered: boolean }[]>(directory, { operation: 'recover' }, 'create')
      .then((result) => { if (result.some((item) => !item.recovered)) app.log.warn('Some project creations require retry; all pending files were preserved.'); })
      .catch(() => app.log.warn('Project creation recovery is unavailable. Pending data was preserved.'));
  });
  app.get('/options', async (request, reply) => {
    sessions.session(request, reply);
    const [options, vms] = await Promise.all([
      projectStore<ProjectOptions>(directory, { operation: 'options' }, 'sdk'),
      projectStore<Pick<ProjectOptions, 'vms' | 'vmsAvailable'>>(directory, { operation: 'vms' }),
    ]);
    return { ...options, ...vms };
  });
  app.get('/vms', async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'vms' });
  });
  app.get<{ Params: { id: string } }>('/:id', { schema: { params: { type: 'object', required: ['id'], properties: { id: identity } } } }, async (request, reply) => {
    sessions.session(request, reply);
    return { project: await projectStore<Project>(directory, { operation: 'get', id: request.params.id }) };
  });
  app.post<{ Body: ProjectInput }>('/', {
    bodyLimit: 32 * 1024,
    preValidation: async (request) => validateFields(request.body, [...Object.keys(fields), 'language', 'template', 'optionsRevision', 'requestId', 'guestFormats']),
    schema: { body: { type: 'object', additionalProperties: false, required: ['name', 'language', 'template', 'optionsRevision', 'requestId'], properties: {
      ...fields, language: { enum: ['Rust', 'Zig', 'C'] },
      template: { enum: ['terminal', 'desktop', 'service', 'driver', 'protocol', 'library', 'subsystem'] },
      optionsRevision: { type: 'string', pattern: '^[a-f0-9]{64}$' }, requestId: identity,
      guestFormats: { type: 'array', maxItems: 8, uniqueItems: true, items: { type: 'string', minLength: 1, maxLength: 63, pattern: '^[a-z](?:[a-z0-9_.-]*[a-z0-9])?$' } },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const input = { ...request.body, description: request.body.description ?? '', vmId: request.body.vmId ?? null, guestFormats: request.body.guestFormats ?? [] };
    const project = await projectStore<Project>(directory, { operation: 'create', input }, 'create');
    return reply.code(201).send({ project });
  });
  app.patch<{ Params: { id: string }; Body: ProjectUpdate }>('/:id', {
    preValidation: async (request) => validateFields(request.body, [...Object.keys(fields), 'revision']),
    schema: { params: { type: 'object', required: ['id'], properties: { id: identity } },
      body: { type: 'object', additionalProperties: false, minProperties: 2, required: ['revision'], properties: {
        ...fields, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return { project: await projectStore<Project>(directory, { operation: 'update', id: request.params.id, input: request.body }) };
  });

  app.get<{ Reply: ProjectsResponse | { message: string } }>('/', async (request, reply) => {
    try { return { projects: await listProjects(directory), csrfToken: sessions.session(request, reply, true).token }; }
    catch (error) {
      app.log.error(error, 'Project inventory could not be read.');
      return reply.code(503).send({ message: 'Projects could not be loaded.' });
    }
  });
}
