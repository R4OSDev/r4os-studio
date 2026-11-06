import type { FastifyInstance } from 'fastify';
import type { QuotaWaitCancelInput, QuotaWaitResult } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';
const identity={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
const params={type:'object',additionalProperties:false,required:['id','sessionId'],properties:{id:identity,sessionId:identity}};
type Params={id:string;sessionId:string};
export function quotaWaitRoutes(app:FastifyInstance,security:ProjectSessions,ownerType:'project'|'skill') {
  const base='/:id/sessions/:sessionId/quota-wait';
  const owner=(id:string)=>ownerType==='skill'?{ownerType,ownerId:id}:{projectId:id};
  app.get<{Params:Params}>(base,{schema:{params}},async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost({operation:'quota_wait',...owner(request.params.id),sessionId:request.params.sessionId});
  });
  app.post<{Params:Params;Body:QuotaWaitCancelInput}>(base+'/cancel',{
    bodyLimit:1024,preValidation:async request=>{
      const v=request.body;
      if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!['requestId','waitId','revision'].includes(k))
        ||typeof v.requestId!=='string'||typeof v.waitId!=='string'||!Number.isSafeInteger(v.revision))throw new ProjectError('Unexpected wait cancellation fields.',400);
    },schema:{params,body:{type:'object',additionalProperties:false,required:['requestId','waitId','revision'],properties:{requestId:identity,waitId:identity,revision:{type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER}}}},
  },async(request,reply)=>{
    security.mutation(request,reply);reply.header('Cache-Control','private, no-store');
    const support=await agentHost<{quotaWaitControl?:number}>({operation:'capabilities'});
    if(support.quotaWaitControl!==1)throw new ProjectError('The agent coordinator must adopt this release before stopping a quota wait.',503);
    return agentHost<QuotaWaitResult>({operation:'quota_wait_cancel',...owner(request.params.id),sessionId:request.params.sessionId,input:request.body});
  });
  app.get<{Params:Params&{requestId:string}}>(base+'/requests/:requestId',{
    schema:{params:{...params,required:[...params.required,'requestId'],properties:{...params.properties,requestId:identity}}},
  },async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost<QuotaWaitResult>({operation:'quota_wait_receipt',...owner(request.params.id),sessionId:request.params.sessionId,requestId:request.params.requestId});
  });
}
