import { environmentNoteRoutes } from './environment-note-routes.js';
import { sessionDeletionRoutes } from './deletion-routes.js';
import type { FastifyInstance } from 'fastify';
import type { AgentSession, AgentSessionSummary, SessionCreate, SessionHistory, SessionOptions, SessionUpdate } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { sessionStore } from './store.js';
import { developmentHost } from '../project-development/host.js';
import { ProjectError } from '../projects/store.js';
import type { DevelopmentJobPage } from '../../../../shared/project-development.js';
import { agentHost } from './host.js';
import { attachmentRoutes } from './attachment-routes.js';
import { generatedRoutes } from './generated-routes.js';
import {screenshotRoutes} from './screenshot-routes.js';
import { migrationRoutes } from './migration-routes.js';
import { quotaWaitRoutes } from './quota-wait-routes.js';
import { modelChoiceRoutes } from './model-choice-routes.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = {
  name: { type: 'string', minLength: 1, maxLength: 120 }, providerId: identity,
  model: { type: 'string', minLength: 1, maxLength: 120 }, effort: { type: 'string', maxLength: 30 },
  fastMode: { type: 'boolean' },
};
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
const projectParams = { type: 'object', required: ['id'], properties: { id: identity } };
type SessionParams = { id: string; sessionId: string };

export function agentSessionRoutes(app: FastifyInstance, directory: string, security: ProjectSessions, providers?: string, ownerType: 'project' | 'skill' = 'project') {
  app.get('/web-service', async (request, reply) => {
    security.session(request, reply); reply.header('Cache-Control','private, no-store');
    return agentHost({operation:'web_service'});
  });
  app.put<{Body:{requestId:string;revision:number;searchEndpoint:string|null}}>('/web-service', {
    bodyLimit:4096,schema:{body:{type:'object',additionalProperties:false,required:['requestId','revision','searchEndpoint'],properties:{
      requestId:identity,revision:{type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER},
      searchEndpoint:{anyOf:[{type:'string',maxLength:2048},{type:'null'}]},
    }}},
  },async(request,reply)=>{
    security.mutation(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost({operation:'set_web_service',input:request.body});
  });
  environmentNoteRoutes(app, security, ownerType);
  sessionDeletionRoutes(app, security, ownerType);
  attachmentRoutes(app, directory, security, ownerType, providers);
  generatedRoutes(app, directory, security, ownerType);
  screenshotRoutes(app,directory,security,providers,ownerType);
  migrationRoutes(app,security,ownerType);
  modelChoiceRoutes(app,security,ownerType);
  quotaWaitRoutes(app,security,ownerType);
  const route = '/:id/sessions';
  const owner = (id: string) => ownerType === 'skill' ? { ownerType, ownerId: id } : { projectId: id };
  if (ownerType === 'project') app.get<{ Params: SessionParams & { jobId: string; evidenceId: string } }>(route + '/:sessionId/images/:jobId/:evidenceId', {
    schema: { params: { ...params, required: ['id', 'sessionId', 'jobId', 'evidenceId'],
      properties: { ...params.properties, jobId: identity, evidenceId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    const { id, sessionId, jobId, evidenceId } = request.params;
    await sessionStore<AgentSession>(directory, { operation: 'get', projectId: id, sessionId }, providers);
    type Image = { metadata: { kind: string; id: string; projectId: string; jobId: string; bytes: number }; base64: string };
    const read = { operation: 'evidence', projectId: id, id: jobId, evidenceId };
    let image: Image;
    try { image = await developmentHost<Image>({ ...read, presentationSessionId: sessionId }); }
    catch (error) {
      if (!(error instanceof ProjectError) || error.statusCode !== 400 || error.message !== 'Unsupported development coordinator operation.') throw error;
      // Older coordinators keep their live workers. Establish session ownership
      // with a read before fetching exactly the same immutable image once.
      const page = await developmentHost<DevelopmentJobPage>({ operation: 'read_job', projectId: id, id: jobId });
      if (page.job.sessionId !== sessionId) throw new ProjectError('This screenshot belongs to another session.', 403);
      image = await developmentHost<Image>(read);
    }
    if (image.metadata.kind !== 'screenshot' || image.metadata.id !== evidenceId || image.metadata.projectId !== id || image.metadata.jobId !== jobId
      || !Number.isSafeInteger(image.metadata.bytes) || image.metadata.bytes < 1 || image.metadata.bytes > 393216)
      throw new ProjectError('This reference is not a session screenshot.', 403);
    return reply.header('Cache-Control', 'private, no-store').header('X-Content-Type-Options', 'nosniff')
      .header('Content-Disposition', 'inline; filename="screenshot.png"').type('image/png').send(Buffer.from(image.base64, 'base64'));
  });
  app.get<{ Params: { id: string } }>(route + '/options', { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    const result = await sessionStore<SessionOptions>(directory, { operation: 'options', ...owner(request.params.id) }, providers);
    if (ownerType === 'project') result.development = await developmentHost<NonNullable<SessionOptions['development']>>({ operation: 'options', ...owner(request.params.id) }).catch(() => undefined);
    return result;
  });
  app.get<{ Params: { id: string } }>(route, { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    return { sessions: await sessionStore<AgentSessionSummary[]>(directory, { operation: 'list', ...owner(request.params.id) }, providers) };
  });
  app.post<{ Params: { id: string }; Body: SessionCreate }>(route, { bodyLimit: 16 * 1024,
    schema: { params: projectParams, body: { type: 'object', additionalProperties: false, required: ['name', 'providerId', 'model', 'effort', 'requestId'], properties: { ...fields, requestId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const session = await sessionStore<AgentSession>(directory, { operation: 'create', ...owner(request.params.id), input: request.body }, providers);
    return reply.code(201).send({ session });
  });
  app.get<{ Params: SessionParams; Querystring: { providerId?: string; model?: string } }>(route + '/:sessionId/image-capability', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: { providerId: identity, model: { type: 'string', minLength: 1, maxLength: 120 } } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return agentHost({ operation: 'image_generation_capability', ...owner(request.params.id), sessionId: request.params.sessionId, selection: request.query });
  });
  app.get<{ Params: SessionParams }>(route + '/:sessionId', { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'get', ...owner(request.params.id), sessionId: request.params.sessionId }, providers) };
  });
  app.get<{ Params: SessionParams }>(route + '/:sessionId/claude-limits', { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return agentHost({ operation: 'session_claude_limits', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  for (const contract of ['zai', 'connection']) {
    app.get<{ Params: SessionParams }>(route + '/:sessionId/'+contract+'-limits', { schema: { params } }, async (request, reply) => {
      security.session(request, reply);
      return agentHost({ operation: 'session_'+contract+'_limits', ...owner(request.params.id), sessionId: request.params.sessionId });
    });
    app.post<{ Params: SessionParams; Body: { requestId: string; providerRevision: number } }>(route + '/:sessionId/'+contract+'-limits/check', {
      bodyLimit: 1024,
      preValidation: async request => {
        if (request.body && Object.keys(request.body).some(key => !['requestId', 'providerRevision'].includes(key))) throw new ProjectError('Invalid subscription check fields.', 400);
      },
      schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'providerRevision'],
        properties: { requestId: identity, providerRevision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER } } } },
    }, async (request, reply) => {
      security.mutation(request, reply);
      return agentHost({ operation: 'session_'+contract+'_limit_refresh', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body });
    });
    app.get<{ Params: SessionParams & { requestId: string } }>(route + '/:sessionId/'+contract+'-limit-requests/:requestId', {
      schema: { params: { ...params, required: [...params.required, 'requestId'], properties: { ...params.properties, requestId: identity } } },
    }, async (request, reply) => {
      security.session(request, reply);
      return agentHost({ operation: 'session_'+contract+'_limit_receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId });
    });
  }
  app.patch<{ Params: SessionParams; Body: SessionUpdate }>(route + '/:sessionId/settings', { bodyLimit: 16 * 1024,
    preValidation: async (request) => {
      if (request.body && Object.hasOwn(request.body,'contextLimit')) {
        const value=request.body.contextLimit;
        if (!value || typeof value!=='object' || Array.isArray(value) || !['off','global','on'].includes(value.mode)
          || value.budgetTokens!==null && (!Number.isSafeInteger(value.budgetTokens) || value.budgetTokens<1 || value.budgetTokens>10000000)) throw new ProjectError('Invalid context limit settings.',400);
      }
      if(request.body&&Object.hasOwn(request.body,'selectionRevision')&&!Number.isSafeInteger(request.body.selectionRevision))throw new ProjectError('Invalid model-choice revision.',400);
      if (request.body && Object.hasOwn(request.body, 'environmentNotesEnabled') && typeof request.body.environmentNotesEnabled !== 'boolean') throw new ProjectError('Environment notes must be a boolean setting.',400);
      if (request.body && Object.hasOwn(request.body, 'imageGenerationEnabled') && typeof request.body.imageGenerationEnabled !== 'boolean') throw new ProjectError('Image generation must be a boolean setting.',400);
      if (request.body && Object.hasOwn(request.body, 'roadmapEnabled')
        && (ownerType !== 'project' || typeof request.body.roadmapEnabled !== 'boolean')) {
        throw new ProjectError('Roadmap is a boolean setting for project sessions only.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['revision'], minProperties: 2, properties: {
      ...fields, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      selectionRevision:{type:'integer',minimum:0,maximum:Number.MAX_SAFE_INTEGER},
      contextLimit: { type:'object', additionalProperties:false, required:['mode','budgetTokens'], properties: {
        mode:{type:'string',enum:['off','global','on']}, budgetTokens:{anyOf:[{type:'null'},{type:'integer',minimum:1,maximum:10000000}]} } },
      webSearchEnabled: { type: 'boolean' }, environmentNotesEnabled: { type: 'boolean' }, imageGenerationEnabled: { type: 'boolean' },
      ...(ownerType === 'project' ? { roadmapEnabled: { type: 'boolean' } } : {}),
      permissions: { type: 'object', additionalProperties: { type: 'boolean' }, minProperties: 9 },
      skillOverrides: { type: 'object', additionalProperties: { type: 'boolean' }, maxProperties: 256 },
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'update', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body }, providers) };
  });
  app.get<{ Params: SessionParams; Querystring: { before?: number; limit?: number } }>(route + '/:sessionId/history', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: {
      before: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, limit: { type: 'integer', minimum: 1, maximum: 100 },
    } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return sessionStore<SessionHistory>(directory, { operation: 'history', ...owner(request.params.id), sessionId: request.params.sessionId, ...request.query }, providers);
  });
}
