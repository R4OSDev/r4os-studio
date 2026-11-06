import type { FastifyInstance } from 'fastify';
import type { ModelChoiceInput, ModelChoiceResult } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';

const identity={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
const revision={type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER};
const params={type:'object',additionalProperties:false,required:['id','sessionId'],properties:{id:identity,sessionId:identity}};
type Params={id:string;sessionId:string};

export function modelChoiceRoutes(app:FastifyInstance,security:ProjectSessions,ownerType:'project'|'skill') {
  const base='/:id/sessions/:sessionId/model-choice';
  const owner=(id:string)=>ownerType==='skill'?{ownerType,ownerId:id}:{projectId:id};
  app.post<{Params:Params;Body:ModelChoiceInput}>(base,{
    bodyLimit:4096,preValidation:async request=>{
      const value=request.body;
      if(!value||typeof value!=='object'||Array.isArray(value)
        ||Object.keys(value).some(key=>!['requestId','revision','selectionRevision','afterRunId','model','effort','fastMode'].includes(key))
        ||typeof value.fastMode!=='boolean'||!Number.isSafeInteger(value.revision)||!Number.isSafeInteger(value.selectionRevision)
        ||['requestId','afterRunId','model','effort'].some(key=>typeof value[key as keyof ModelChoiceInput]!=='string'))
        throw new ProjectError('Unexpected next-run model fields.',400);
    },schema:{params,body:{type:'object',additionalProperties:false,
      required:['requestId','revision','selectionRevision','afterRunId','model','effort','fastMode'],properties:{
        requestId:identity,revision,selectionRevision:{...revision,minimum:0},afterRunId:identity,
        model:{type:'string',minLength:1,maxLength:200},effort:{type:'string',maxLength:30},fastMode:{type:'boolean'},
      }}},
  },async(request,reply)=>{
    security.mutation(request,reply);reply.header('Cache-Control','private, no-store');
    const support=await agentHost<{deferredModelChoice?:number}>({operation:'capabilities'});
    if(support.deferredModelChoice!==1)throw new ProjectError('The agent coordinator must adopt this Studio release before accepting a next-run model choice.',503);
    return agentHost<ModelChoiceResult>({operation:'choose_model',...owner(request.params.id),sessionId:request.params.sessionId,input:request.body});
  });
  app.get<{Params:Params&{requestId:string}}>(base+'/requests/:requestId',{
    schema:{params:{...params,required:[...params.required,'requestId'],properties:{...params.properties,requestId:identity}}},
  },async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return agentHost<ModelChoiceResult>({operation:'model_choice_receipt',...owner(request.params.id),sessionId:request.params.sessionId,requestId:request.params.requestId});
  });
}
