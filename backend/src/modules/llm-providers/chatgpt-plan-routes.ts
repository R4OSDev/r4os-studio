import type { FastifyInstance, FastifyRequest } from 'fastify';
import { readFile } from 'node:fs/promises';
import { agentHost } from '../agent-sessions/host.js';
import type { ProviderSessions } from './sessions.js';

const uuid = { type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const input = { type:'object',additionalProperties:false,required:['requestId','name'],properties:{
  requestId:uuid,name:{type:'string',minLength:1,maxLength:80},providerId:uuid,previousAttempt:uuid,
} };
function localBrowser(request: FastifyRequest) {
  try { const origin=new URL(request.headers.origin ?? '');return ['127.0.0.1','::1','::ffff:127.0.0.1'].includes(request.ip)&&['127.0.0.1','localhost','[::1]'].includes(origin.hostname); }
  catch { return false; }
}
export function chatgptPlanRoutes(app: FastifyInstance, security: ProviderSessions) {
  app.get('/chatgpt-plan',async(request,reply)=>{const owner=security.get(request,reply).id;reply.header('Cache-Control','private, no-store');return agentHost({operation:'chatgpt_plan',action:'list',ownerId:owner});});
  app.get('/chatgpt-plan/helper',async(request,reply)=>{
    security.get(request,reply);return reply.header('Cache-Control','private, no-store').header('X-Content-Type-Options','nosniff')
      .header('Content-Disposition','attachment; filename="r4os-studio-chatgpt-login.mjs"').type('text/javascript')
      .send(await readFile(new URL('../../../../scripts/agent-sessions/chatgpt_plan_auth.mjs',import.meta.url)));
  });
  app.post<{Body:{requestId:string}}>('/chatgpt-plan/prepare',{schema:{body:{type:'object',additionalProperties:false,required:['requestId'],properties:{requestId:uuid}}}},async(request,reply)=>{
    const owner=security.mutation(request,reply);return agentHost({operation:'chatgpt_plan',action:'prepare',ownerId:owner,requestId:request.body.requestId});
  });
  app.post<{Body:unknown}>('/chatgpt-plan/login',{bodyLimit:4096,schema:{body:input}},async(request,reply)=>{
    const owner=security.mutation(request,reply);return agentHost({operation:'chatgpt_plan',action:'start',ownerId:owner,input:request.body,localBrowser:localBrowser(request)});
  });
  app.post<{Body:unknown}>('/chatgpt-plan/import',{bodyLimit:4096,schema:{body:{...input,required:['requestId','name','importId'],properties:{...input.properties,importId:uuid}}}},async(request,reply)=>{
    const owner=security.mutation(request,reply);return agentHost({operation:'chatgpt_plan',action:'import',ownerId:owner,input:request.body});
  });
  for(const action of ['cancel','finish'])app.post<{Params:{requestId:string}}>('/chatgpt-plan/attempts/:requestId/'+action,{schema:{params:{type:'object',additionalProperties:false,required:['requestId'],properties:{requestId:uuid}}}},async(request,reply)=>{
    const owner=security.mutation(request,reply);return agentHost({operation:'chatgpt_plan',action,ownerId:owner,requestId:request.params.requestId});
  });
}
