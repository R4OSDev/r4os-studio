import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError, projectStore } from '../projects/store.js';
import { gitHost } from './client.js';
import { projectBinding } from '../github-connections/references.js';
import { developmentHost } from '../project-development/host.js';
import {dirname,join} from 'node:path';
import { ProjectGitHubRefresh } from './refresh.js';
import type {GitHubIssueState} from '../../../../shared/project-github-issues.js';

export async function projectGithubRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions,{
  githubDirectory=join(dirname(directory),'GitHub'), transport=fetch, refreshGithub=false,
}:{githubDirectory?:string;transport?:typeof fetch;refreshGithub?:boolean}={}) {
  const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
  const params = { type: 'object', required: ['id'], properties: { id: uuid, requestId: uuid } };
  const refresh = new ProjectGitHubRefresh(directory, githubDirectory, transport);
  const { issues } = refresh;
  if (refreshGithub) {
    const stop = new AbortController();
    let pending: Promise<unknown> | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = () => {
      pending = refresh.runDue(stop.signal).catch(() => app.log.warn('GitHub refresh will retry at its next scheduled check.')).finally(() => {
        if (!stop.signal.aborted) timer = setTimeout(tick, refresh.nextDelay).unref();
      });
    };
    app.addHook('onListen', async () => { timer = setTimeout(tick, 1000).unref(); });
    app.addHook('onClose', async () => { stop.abort(); clearTimeout(timer); await pending; });
  }
  app.get<{Params:{id:string}}>('/:id/github/observation',{schema:{params}},async(request,reply)=>{
    sessions.session(request,reply);
    return refresh.status(request.params.id);
  });
  app.get('/github/issue-counts',async(request,reply)=>{
    sessions.session(request,reply);
    return refresh.issueCounts();
  });
  app.post<{Params:{id:string};Body:{bindingRevision:number;requestId:string}}>('/:id/github/refresh',{
    bodyLimit:4096,schema:{params,body:{type:'object',required:['bindingRevision','requestId'],additionalProperties:false,
      properties:{bindingRevision:{type:'integer',minimum:1},requestId:uuid}}},
  },async(request,reply)=>{
    sessions.mutation(request,reply);
    const binding=await refresh.readBinding(request.params.id);
    if(!binding||binding.revision!==request.body.bindingRevision)throw new ProjectError('The repository connection changed. Refresh again.',409);
    const stop = new AbortController();
    const disconnected = () => stop.abort();
    reply.raw.once('close', disconnected);
    try { return await refresh.check(request.params.id,binding,request.body.requestId,stop.signal); }
    finally { reply.raw.off('close', disconnected); }
  });
  app.get<{Params:{id:string};Querystring:{bindingRevision:number}}>('/:id/github/issues/saved',{
    schema:{params,querystring:{type:'object',required:['bindingRevision'],properties:{bindingRevision:{type:'integer',minimum:1}}}},
  },async(request,reply)=>{
    sessions.session(request,reply);reply.header('Cache-Control','private, no-store');
    return {page:await issues.saved(request.params.id,request.query.bindingRevision)};
  });
  app.get<{Params:{id:string};Querystring:{bindingRevision:number;state?:GitHubIssueState;cursor?:string;refresh?:boolean}}>('/:id/github/issues',{
    preValidation:async request=>{if(Object.keys(request.query as object).some(key=>!['bindingRevision','state','cursor','refresh'].includes(key)))throw new ProjectError('Unexpected issue query fields.',400);},
    schema:{params,querystring:{type:'object',additionalProperties:false,required:['bindingRevision'],properties:{
      bindingRevision:{type:'integer',minimum:1},state:{type:'string',enum:['open','closed','all']},cursor:{type:'string',minLength:1,maxLength:4096},refresh:{type:'boolean'}
    }}}
  },async(request,reply)=>{
    sessions.session(request,reply);reply.header('Cache-Control','private, no-store');
    return issues.read(request.params.id,request.query.bindingRevision,request.query.state??'open',request.query.cursor??null,request.query.refresh===true);
  });
  app.get('/github/capabilities', async (request, reply) => {
    sessions.session(request, reply);
    return gitHost({ operation: 'capabilities' }).catch(() => ({ available: false, protocol: 1, reason: 'Git host support is unavailable.' }));
  });
  app.post<{ Body: { requestId: string; connectionId: string; tokenRevision: number; userId: number; repository: { id: number; owner: string; name: string }; branch: string } }>('/github/imports', {
    bodyLimit: 32768, schema: { body: { type: 'object', required: ['requestId', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch'], properties: { requestId: uuid, connectionId: uuid, tokenRevision: { type: 'integer', minimum: 1 }, userId: { type: 'integer', minimum: 1 }, repository: { type: 'object', required: ['id', 'owner', 'name'], properties: { id: { type: 'integer', minimum: 1 }, owner: { type: 'string', maxLength: 39 }, name: { type: 'string', maxLength: 100 } } }, branch: { type: 'string', maxLength: 255 } } } },
    preValidation: async (request) => {
      const body = request.body as Record<string, unknown> | null;
      if (!body || Object.keys(body).some((key) => !['requestId', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch'].includes(key))) throw new ProjectError('Unexpected import fields.', 400);
      if (body.repository && typeof body.repository === 'object' && Object.keys(body.repository).some((key) => !['id', 'owner', 'name'].includes(key))) throw new ProjectError('Unexpected repository fields.', 400);
    },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const { requestId, ...input } = request.body;
    return gitHost({ operation: 'submit', projectId: requestId, requestId, kind: 'import', input });
  });
  app.post<{ Params: { requestId: string }; Body: Record<string, unknown> }>('/github/imports/:requestId/finish', {
    bodyLimit: 32768, schema: { params: { type: 'object', required: ['requestId'], properties: { requestId: uuid } } },
    preValidation: async (request) => {
      const body = request.body as Record<string, unknown> | null;
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).some((key) => !['name', 'description', 'snapshot', 'fallback', 'remoteHostId', 'vmId'].includes(key))) throw new ProjectError('Unexpected import completion fields.', 400);
      for (const key of ['vmId', 'remoteHostId']) if (body[key] !== undefined && body[key] !== null && (typeof body[key] !== 'string' || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(body[key] as string))) throw new ProjectError('Choose an existing local target.', 400);
    },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return developmentHost({ operation: 'github_import_finish', projectId: request.params.requestId, input: request.body });
  });
  app.post<{ Params: { id: string; requestId: string } }>('/:id/github/pulls/:requestId/validate', { schema: { params, body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return developmentHost({ operation: 'github_pull_validate', projectId: request.params.id, input: { requestId: request.params.requestId } });
  });
  app.get<{ Params: { id: string } }>('/:id/github', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    await projectStore(directory, { operation: 'get_settings', id: request.params.id });
    const job = await gitHost({ operation: 'last_job', projectId: request.params.id }).catch(() => null);
    return { binding: await projectBinding(directory, request.params.id), job };
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; kind: string; input: Record<string, unknown> } }>('/:id/github/jobs', {
    bodyLimit: 32768, preValidation: async (request) => {
      if (!request.body || typeof request.body !== 'object' || Array.isArray(request.body) || Object.keys(request.body).some((key) => !['requestId', 'kind', 'input'].includes(key))) throw new ProjectError('Unexpected Git job request fields.', 400);
    }, schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'kind', 'input'], properties: {
      requestId: uuid, kind: { type: 'string', enum: ['initialize', 'status', 'check', 'diff', 'bind', 'create_repository', 'push', 'prepare_pull', 'pull'] }, input: { type: 'object' },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const { kind, input } = request.body;
    const keys = kind === 'bind' ? ['expectedRevision', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch', 'author']
      : kind === 'create_repository' ? ['connectionId', 'tokenRevision', 'userId', 'repositoryName', 'private', 'owner'] : kind === 'check' ? ['bindingRevision'] : kind === 'diff' ? ['path', 'snapshot'] : kind === 'push' ? ['bindingRevision', 'snapshot', 'commitMessage', 'files'] : kind === 'prepare_pull' ? ['bindingRevision', 'snapshot', 'remoteHead'] : kind === 'pull' ? ['preparationId', 'bindingRevision', 'snapshot'] : [];
    if (Object.keys(input).some((key) => !keys.includes(key))) throw new ProjectError('Unexpected Git job fields.', 400);
    return gitHost({ operation: 'submit', projectId: request.params.id, ...request.body });
  });
  app.get<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    return gitHost({ operation: 'job', projectId: request.params.id, requestId: request.params.requestId });
  });
  app.post<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId/stop', { schema: { params, body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return gitHost({ operation: 'cancel', projectId: request.params.id, requestId: request.params.requestId });
  });
  app.post<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId/reconcile', { schema: { params, body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return gitHost({ operation: 'reconcile', projectId: request.params.id, requestId: request.params.requestId });
  });
}
