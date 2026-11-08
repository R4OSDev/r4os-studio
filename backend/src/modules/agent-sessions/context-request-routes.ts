import type {FastifyInstance} from 'fastify';
import type {ProjectSessions} from '../projects/sessions.js';
import type {ContextRequestPage,ContextRequestDetail,ContextRequestChunk} from '../../../../shared/context-requests.js';
import {sessionStore} from './store.js';

const identity={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
const integer={type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER};
const params={type:'object',additionalProperties:false,required:['id','sessionId'],properties:{id:identity,sessionId:identity}};
const member={...params,required:['id','sessionId','requestId'],properties:{...params.properties,requestId:identity}};
type Params={id:string;sessionId:string};
type Member=Params&{requestId:string};
export function contextRequestRoutes(app:FastifyInstance,directory:string,security:ProjectSessions,providers:string|undefined,ownerType:'project'|'skill') {
  const owner=(id:string)=>ownerType==='skill'?{ownerType,ownerId:id}:{projectId:id};
  const route='/:id/sessions/:sessionId/context-requests';
  app.get<{Params:Params;Querystring:{before?:number;limit?:number}}>(route,{
    schema:{params,querystring:{type:'object',additionalProperties:false,properties:{before:integer,limit:{type:'integer',minimum:1,maximum:50}}}},
  },async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return sessionStore<ContextRequestPage>(directory,{operation:'context_requests',...owner(request.params.id),sessionId:request.params.sessionId,...request.query},providers);
  });
  app.get<{Params:Member}>(route+'/:requestId',{schema:{params:member}},async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return sessionStore<ContextRequestDetail>(directory,{operation:'context_request',...owner(request.params.id),sessionId:request.params.sessionId,requestId:request.params.requestId},providers);
  });
  app.get<{Params:Member;Querystring:{offset?:number;limit?:number}}>(route+'/:requestId/body',{
    schema:{params:member,querystring:{type:'object',additionalProperties:false,properties:{offset:{...integer,minimum:0},limit:{type:'integer',minimum:1,maximum:65536}}}},
  },async(request,reply)=>{
    security.session(request,reply);reply.header('Cache-Control','private, no-store');
    return sessionStore<ContextRequestChunk>(directory,{operation:'context_request_body',...owner(request.params.id),sessionId:request.params.sessionId,requestId:request.params.requestId,...request.query},providers);
  });
  app.get<{Params:Member}>(route+'/:requestId/download',{schema:{params:member}},async(request,reply)=>{
    security.session(request,reply);
    const {id,sessionId,requestId}=request.params;
    // Full body only on explicit request. Keep default bridge/list limits small.
    const original=await sessionStore<ContextRequestChunk>(directory,{operation:'context_request_body',...owner(id),sessionId,requestId,limit:8*1024*1024},providers,12*1024*1024);
    return reply.header('Cache-Control','private, no-store').header('X-Content-Type-Options','nosniff')
      .header('Content-Disposition',`attachment; filename="llm-request-${requestId}.json"`)
      .type('application/json; charset=utf-8').send(Buffer.from(original.base64,'base64'));
  });
}
