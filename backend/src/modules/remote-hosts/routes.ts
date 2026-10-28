import type { FastifyInstance } from 'fastify';
import type { RemoteHost, RemoteHostCapabilities, RemoteHostCheck } from '../../../../shared/remote-hosts.js';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { remoteHostStore } from './store.js';
import { remoteHostBroker } from './broker.js';

export async function remoteHostRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('remote-hosts');
  app.setErrorHandler((error, _request, reply) => {
    const known = error instanceof ProjectError;
    const code = known ? error.statusCode : (error as { statusCode?: number }).statusCode;
    void reply.code(known ? code! : code === 413 ? 413 : code === 400 ? 400 : 503).send({ message: known ? error.message : 'The Remote Host request could not be completed. Existing data was preserved.' });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
    else if (request.url.split('?')[0].replace(/\/$/, '') !== '/api/remote-hosts') sessions.session(request, reply);
  });
  app.get('/', async (request, reply) => ({ hosts: await remoteHostStore<RemoteHost[]>(directory, { operation: 'list' }), csrfToken: sessions.session(request, reply, true).token }));
  app.get<{ Params: { id: string } }>('/:id', async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'get', id: request.params.id }));
  app.get('/capabilities', async (): Promise<RemoteHostCapabilities> => {
    try {
      const value = await remoteHostBroker<RemoteHostCapabilities>({ protocol: 1, operation: 'capabilities' });
      return { protocol: 1, test: value.test === true, commands: value.commands === true, files: value.files === true, ...(value.lifecycle === 1 ? { lifecycle: 1 as const } : {}) };
    }
    catch { return { protocol: 1, test: false, commands: false, files: false, reason: 'Remote host connection support is unavailable.' }; }
  });
  app.post('/', { bodyLimit: 16384 }, async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'create', input: request.body }));
  app.patch<{ Params: { id: string } }>('/:id', { bodyLimit: 16384 }, async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'update', id: request.params.id, input: request.body }));
  app.delete<{ Params: { id: string } }>('/:id', { bodyLimit: 4096 }, async (request) => remoteHostStore<{ id: string; removed: true }>(directory, { operation: 'remove', id: request.params.id, input: request.body }));
  app.post<{ Params: { id: string } }>('/:id/test', { bodyLimit: 4096 }, async (request) => remoteHostBroker<RemoteHostCheck>({ protocol: 1, operation: 'test', hostId: request.params.id, input: request.body }));
  app.get<{ Params: { id: string; requestId: string } }>('/:id/tests/:requestId', async (request) => remoteHostBroker<RemoteHostCheck>({ protocol: 1, operation: 'read', hostId: request.params.id, requestId: request.params.requestId }));
  app.post<{ Params: { id: string } }>('/:id/trust', { bodyLimit: 4096 }, async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'reset_trust', id: request.params.id, input: request.body }));
  app.get<{ Params: { id: string } }>('/:id/jobs', async (request) => remoteHostBroker({ protocol: 1, operation: 'jobs', hostId: request.params.id }));
  app.get<{ Params: { id: string; projectId: string; jobId: string } }>('/:id/jobs/:projectId/:jobId', async (request) => remoteHostBroker({ protocol: 1, operation: 'job', hostId: request.params.id, projectId: request.params.projectId, jobId: request.params.jobId }));
  app.post<{ Params: { id: string; projectId: string; jobId: string } }>('/:id/jobs/:projectId/:jobId/review', { bodyLimit: 4096 }, async (request) => remoteHostBroker({ protocol: 1, operation: 'review_job', hostId: request.params.id, projectId: request.params.projectId, jobId: request.params.jobId, input: request.body }));
  app.get<{ Params: { id: string; projectId: string; jobId: string; requestId: string } }>('/:id/jobs/:projectId/:jobId/reviews/:requestId', async (request) => remoteHostBroker({ protocol: 1, operation: 'review_receipt', hostId: request.params.id, projectId: request.params.projectId, jobId: request.params.jobId, requestId: request.params.requestId }));
}
