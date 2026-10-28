import type {FastifyInstance} from 'fastify';
import type {ProjectSessions} from '../projects/sessions.js';
import {agentHost} from './host.js';
const uuid={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'},integer={type:'integer',minimum:0,maximum:Number.MAX_SAFE_INTEGER};
const params={type:'object',additionalProperties:false,required:['id','sessionId'],properties:{id:uuid,sessionId:uuid}};
type Params={id:string;sessionId:string};
export function environmentNoteRoutes(app:FastifyInstance,security:ProjectSessions,ownerType:'project'|'skill'){
 const base='/:id/sessions/:sessionId/environment-notes',scope=(p:Params)=>({ownerType,ownerId:p.id,sessionId:p.sessionId});
 app.get<{Params:Params;Querystring:Record<string,unknown>}>(base,{schema:{params,querystring:{type:'object',additionalProperties:false,properties:{before:{...integer,minimum:1},limit:{type:'integer',minimum:1,maximum:50},query:{type:'string',maxLength:160},kind:{type:'string',enum:['problem','suggestion']},category:{type:'string',enum:['tools','capabilities','workflow','interface','documentation']},id:uuid}}}},async(request,reply)=>{
  security.session(request,reply);reply.header('Cache-Control','private, no-store');return agentHost({operation:'environment_notes',...scope(request.params),query:request.query});
 });
 app.get<{Params:Params&{requestId:string}}>(base+'/requests/:requestId',{schema:{params:{...params,required:[...params.required,'requestId'],properties:{...params.properties,requestId:uuid}}}},async(request,reply)=>{
  security.session(request,reply);reply.header('Cache-Control','private, no-store');return agentHost({operation:'environment_note_receipt',...scope(request.params),requestId:request.params.requestId});
 });
 app.delete<{Params:Params&{noteId:string};Body:{requestId:string;collectionRevision:number;revision:number}}>(base+'/:noteId',{bodyLimit:2048,schema:{params:{...params,required:[...params.required,'noteId'],properties:{...params.properties,noteId:uuid}},body:{type:'object',additionalProperties:false,required:['requestId','collectionRevision','revision'],properties:{requestId:uuid,collectionRevision:integer,revision:{...integer,minimum:1}}}}},async(request,reply)=>{
  security.mutation(request,reply);reply.header('Cache-Control','private, no-store');return agentHost({operation:'delete_environment_notes',...scope(request.params),noteId:request.params.noteId,input:request.body});
 });
 app.post<{Params:Params;Body:{requestId:string;collectionRevision:number;confirmName:string;count:number}}>(base+'/delete-all',{bodyLimit:2048,schema:{params,body:{type:'object',additionalProperties:false,required:['requestId','collectionRevision','confirmName','count'],properties:{requestId:uuid,collectionRevision:integer,confirmName:{type:'string',maxLength:120},count:{...integer,maximum:200}}}}},async(request,reply)=>{
  security.mutation(request,reply);reply.header('Cache-Control','private, no-store');return agentHost({operation:'delete_environment_notes',...scope(request.params),input:request.body});
 });
}
