import { scopedStatisticsRoutes } from '../statistics/routes.js';
import type { FastifyInstance } from 'fastify';
import type { Skill, SkillDetail, SkillFileContent, SkillValidation } from '../../../../shared/skills.js';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { skillStore } from './store.js';
import { agentHost } from '../agent-sessions/host.js';
import { agentSessionRoutes } from '../agent-sessions/routes.js';
import { runRoutes } from '../agent-sessions/run-routes.js';
import { dirname, join } from 'node:path';

function body(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProjectError('Invalid skill request.', 400);
  return value as Record<string, unknown>;
}
export async function skillRoutes(app: FastifyInstance, { directory, providerDirectory }: { directory: string; providerDirectory?: string }) {
  const sessions = new ProjectSessions('skills');
  scopedStatisticsRoutes(app, sessions, 'skill');
  app.setErrorHandler((cause, _request, reply) => {
    if ((cause as { code?: string }).code === 'FST_ERR_CTP_BODY_TOO_LARGE')
      return reply.code(413).send({ message: 'The request exceeds the allowed file size.' });
    const error = cause instanceof ProjectError ? cause : new ProjectError('The skill request could not be completed.', 400);
    void reply.code(error.statusCode).send({ message: error.message });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
  });
  agentSessionRoutes(app, join(dirname(directory), 'Projects'), sessions, providerDirectory, 'skill');
  runRoutes(app, sessions, 'skill');
  app.get('/', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    return { skills: await skillStore<Skill[]>(directory, { operation: 'list' }), csrfToken: session.token };
  });
  const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
  const deletionParams = { type: 'object', required: ['id'], additionalProperties: false, properties: { id: identity } };
  app.get<{Params:{id:string}}>('/:id/deletion', {schema:{params:deletionParams}}, async(request,reply)=>{
    sessions.session(request,reply);return agentHost({operation:'skill_delete_preview',ownerId:request.params.id});
  });
  app.get<{Params:{id:string;requestId:string}}>('/:id/deletion/:requestId', {schema:{params:{...deletionParams,required:['id','requestId'],properties:{id:identity,requestId:identity}}}}, async(request,reply)=>{
    sessions.session(request,reply);return agentHost({operation:'skill_delete_receipt',ownerId:request.params.id,requestId:request.params.requestId});
  });
  app.post<{Params:{id:string};Body:{requestId:string;revision:number;scopeHash:string;confirmName:string}}>('/:id/deletion', {bodyLimit:2048,schema:{params:deletionParams,body:{type:'object',additionalProperties:false,required:['requestId','revision','scopeHash','confirmName'],properties:{requestId:identity,revision:{type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER},scopeHash:{type:'string',pattern:'^[a-f0-9]{64}$'},confirmName:{type:'string',maxLength:120}}}}}, async(request,reply)=>{
    const support=await agentHost<{skillDeletion?:number}>({operation:'capabilities'});
    if(support.skillDeletion!==1)throw new ProjectError('Wait for the agent coordinator to adopt safe skill deletion.',503);
    const result=await agentHost<{state:string}>({operation:'skill_delete',ownerId:request.params.id,input:request.body});
    return reply.code(result.state==='deleted'?200:202).send(result);
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
