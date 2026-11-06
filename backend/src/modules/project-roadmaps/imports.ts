import type {FastifyInstance} from 'fastify';
import {createHash} from 'node:crypto';
import type {ProjectSessions} from '../projects/sessions.js';
import {ProjectError} from '../projects/store.js';
import {roadmapStore} from './store.js';
import {uploadRoadmapJson} from './import-store.js';

const uuid={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
type Params={id:string;fileId:string;previewId:string;requestId:string};
const base='/:id/roadmap/json-imports';
export function roadmapImportRoutes(app:FastifyInstance,directory:string,sessions:ProjectSessions){
 const uploads=new Set<object>();
 const params=(names:string[])=>({type:'object',required:names,properties:Object.fromEntries(names.map(k=>[k,uuid]))});
 app.post<{Params:Params;Body:Buffer}>(base+'/files/:fileId',{
  bodyLimit:16*1024*1024,schema:{params:params(['id','fileId'])},
  onRequest:async(request,reply)=>{
   sessions.mutation(request,reply);
   if(request.headers['content-type']?.split(';',1)[0].trim()!=='application/octet-stream'||request.headers['content-encoding'])throw new ProjectError('Upload raw JSON file bytes as application/octet-stream without content encoding.',415);
   if(uploads.size>=2)throw new ProjectError('Two JSON uploads are already active.',429);
   uploads.add(request);request.raw.once('aborted',()=>uploads.delete(request));
   await roadmapStore(directory,{operation:'revision',projectId:request.params.id});
  },onResponse:async(request)=>{uploads.delete(request);},onError:async(request)=>{uploads.delete(request);},
 },async(request)=>{
  if(!Buffer.isBuffer(request.body)||!request.body.length)throw new ProjectError('Upload a complete nonempty JSON file.',400);
  return uploadRoadmapJson(directory,{projectId:request.params.id,fileId:request.params.fileId,sha256:createHash('sha256').update(request.body).digest('hex'),byteLength:request.body.length},request.body);
 });
 app.get<{Params:Params}>(base+'/files/:fileId',{schema:{params:params(['id','fileId'])}},async(request,reply)=>{
  sessions.session(request,reply);return roadmapStore(directory,{operation:'export_info',projectId:request.params.id,exportId:request.params.fileId});
 });
 for(const [path,operation] of [['previews','import_preview'],['apply','import_apply']] as const){
  app.post<{Params:Params;Body:unknown}>(base+'/'+path,{bodyLimit:128*1024,schema:{params:params(['id'])}},async(request,reply)=>{
   sessions.mutation(request,reply);return roadmapStore(directory,{operation,projectId:request.params.id,input:request.body});
  });
 }
 for(const chunk of [false,true])app.get<{Params:Params;Querystring:{offset?:number;limit?:number}}>(base+'/previews/:previewId'+(chunk?'/chunks':''),{schema:{params:params(['id','previewId']),querystring:{type:'object',additionalProperties:false,properties:chunk?{offset:{type:'integer',minimum:0,maximum:64*1024*1024},limit:{type:'integer',minimum:4,maximum:65536}}:{}}}},async(request,reply)=>{
  sessions.session(request,reply);return roadmapStore(directory,{operation:chunk?'import_preview_chunk':'import_preview_read',projectId:request.params.id,previewId:request.params.previewId,...request.query});
 });
 app.get<{Params:Params}>(base+'/requests/:requestId',{schema:{params:params(['id','requestId'])}},async(request,reply)=>{
  sessions.session(request,reply);return roadmapStore(directory,{operation:'import_receipt',projectId:request.params.id,requestId:request.params.requestId});
 });
}
