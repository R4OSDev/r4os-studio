import type { FastifyInstance } from 'fastify';
import { agentHost } from '../agent-sessions/host.js';
import type { ProviderSessions } from './sessions.js';

const uuid = { type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const input = { type:'object',additionalProperties:false,required:['requestId','name'],properties:{
  requestId:uuid,name:{type:'string',minLength:1,maxLength:80},providerId:uuid,previousAttempt:uuid,
} };
export function chatgptPlanRoutes(app: FastifyInstance, security: ProviderSessions) {
  for (const contract of ['chatgpt-plan', 'claude-plan']) {
    const base = '/'+contract, operation = contract.replaceAll('-', '_');
    app.get(base,async(request,reply)=>{const owner=security.get(request,reply).id;reply.header('Cache-Control','private, no-store');return agentHost({operation,action:'list',ownerId:owner});});
    app.post<{Body:unknown}>(base+'/login',{bodyLimit:4096,schema:{body:input}},async(request,reply)=>{
      const owner=security.mutation(request,reply);reply.header('Cache-Control','private, no-store');return agentHost({operation,action:'start',ownerId:owner,input:request.body});
    });
    app.post<{Params:{requestId:string};Body:{redirectUrl:string}}>(base+'/attempts/:requestId/redirect',{
      bodyLimit:32768,schema:{params:{type:'object',additionalProperties:false,required:['requestId'],properties:{requestId:uuid}},
        body:{type:'object',additionalProperties:false,required:['redirectUrl'],properties:{redirectUrl:{type:'string',minLength:1,maxLength:16384}}}},
    },async(request,reply)=>{
      const owner=security.mutation(request,reply);reply.header('Cache-Control','private, no-store');
      return agentHost({operation,action:'callback',ownerId:owner,requestId:request.params.requestId,redirectUrl:request.body.redirectUrl});
    });
    for(const action of contract === 'chatgpt-plan' ? ['cancel','finish'] : ['cancel'])app.post<{Params:{requestId:string}}>(base+'/attempts/:requestId/'+action,{schema:{params:{type:'object',additionalProperties:false,required:['requestId'],properties:{requestId:uuid}}}},async(request,reply)=>{
      const owner=security.mutation(request,reply);return agentHost({operation,action,ownerId:owner,requestId:request.params.requestId});
    });
  }
}
