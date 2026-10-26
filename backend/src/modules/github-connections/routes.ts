import type { FastifyInstance } from 'fastify';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { GitHubStore, createInput, changeInput, deleteInput, connectionId, tokenInput } from './store.js';
import { testToken } from './test.js';
import type { GitHubTestResult } from '../../../../shared/github-connections.js';
import { GitHubRepositories } from './repositories.js';
import { connectionProjects } from './references.js';
import { projectsDirectory, ProjectError as InvalidInput } from '../projects/store.js';

export async function githubRoutes(app: FastifyInstance, { directory, projectDirectory = projectsDirectory(), tester = testToken, transport = fetch }: {
  directory: string; projectDirectory?: string; tester?: (token: string) => Promise<GitHubTestResult>; transport?: typeof fetch;
}) {
  const sessions = new ProjectSessions('github'), store = new GitHubStore(directory);
  const repositories = new GitHubRepositories(store, transport);
  function input(value: unknown, keys: string[]) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some((key) => !keys.includes(key))) throw new InvalidInput('Invalid GitHub request.', 400);
    const body = value as Record<string, unknown>;
    if (!Number.isSafeInteger(body.tokenRevision) || (body.tokenRevision as number) < 1) throw new InvalidInput('Invalid token revision.', 400);
    return body;
  }
  function page(value: unknown) { if (value === undefined) return 1; if (!Number.isSafeInteger(value) || (value as number) < 1 || (value as number) > 100) throw new InvalidInput('Invalid result page.', 400); return value as number; }
  let tests = 0;
  async function test(token: string) {
    if (tests >= 4) throw new ProjectError('Too many connection tests are running. Try again shortly.', 409);
    tests++; try { return await tester(token); } finally { tests--; }
  }
  app.setErrorHandler((error, _request, reply) => {
    const known = error instanceof ProjectError;
    const code = error instanceof Error && 'statusCode' in error ? error.statusCode : 503;
    const status = known ? error.statusCode : (code === 413 ? 413 : code === 400 ? 400 : 503);
    void reply.code(status).send({ message: known ? error.message : status === 413 ? 'Connection request is too large.' : 'The connection request could not be completed.' });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
  });
  app.get('/', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    return { connections: await store.list(), csrfToken: session.token };
  });
  app.post('/', { bodyLimit: 16 * 1024 }, async (request) => store.create(createInput(request.body)));
  app.get<{ Params: { id: string } }>('/:id/projects', async (request, reply) => {
    sessions.session(request, reply); connectionId(request.params.id);
    return { projects: await connectionProjects(projectDirectory, request.params.id) };
  });
  app.post<{ Params: { id: string } }>('/:id/account', { bodyLimit: 4096 }, async (request) => {
    connectionId(request.params.id); const body = input(request.body, ['tokenRevision']);
    return (await repositories.account(request.params.id, body.tokenRevision as number)).account;
  });
  app.post<{ Params: { id: string } }>('/:id/repositories', { bodyLimit: 4096 }, async (request) => {
    connectionId(request.params.id); const body = input(request.body, ['tokenRevision', 'page', 'query']);
    if (body.query !== undefined && (typeof body.query !== 'string' || body.query.length > 100)) throw new InvalidInput('Invalid repository search.', 400);
    return repositories.repositories(request.params.id, body.tokenRevision as number, page(body.page), body.query as string | undefined);
  });
  app.post<{ Params: { id: string } }>('/:id/branches', { bodyLimit: 4096 }, async (request) => {
    connectionId(request.params.id); const body = input(request.body, ['tokenRevision', 'page', 'owner', 'name', 'repositoryId']);
    if (!Number.isSafeInteger(body.repositoryId) || (body.repositoryId as number) < 1) throw new InvalidInput('Invalid repository identity.', 400);
    return repositories.branches(request.params.id, body.tokenRevision as number, body.owner as string, body.name as string, body.repositoryId as number, page(body.page));
  });
  app.post('/test', { bodyLimit: 16 * 1024 }, async (request) => test(tokenInput(request.body)));
  app.post<{ Params: { id: string } }>('/:id/test', { bodyLimit: 4096 }, async (request) => {
    connectionId(request.params.id);
    const binding = await store.beginTest(request.params.id, deleteInput(request.body));
    return store.finishTest(request.params.id, binding, await test(binding.token));
  });
  app.patch<{ Params: { id: string } }>('/:id', { bodyLimit: 16 * 1024 }, async (request) => {
    connectionId(request.params.id); return store.update(request.params.id, changeInput(request.body));
  });
  app.delete<{ Params: { id: string } }>('/:id', async (request, reply) => {
    connectionId(request.params.id);
    const body = request.body as { revision: number; confirmProjects?: boolean };
    if (!body || Object.keys(body).some((key) => !['revision', 'confirmProjects'].includes(key)) || (body.confirmProjects !== undefined && body.confirmProjects !== true)) throw new InvalidInput('Invalid removal request.', 400);
    const revision = deleteInput({ revision: body.revision });
    if ((await connectionProjects(projectDirectory, request.params.id)).length && body.confirmProjects !== true) throw new InvalidInput('This connection is used by projects. Confirm their loss of GitHub access before removing it.', 409);
    await store.remove(request.params.id, revision); return reply.code(204).send();
  });
}
