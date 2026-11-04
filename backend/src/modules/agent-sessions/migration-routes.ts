import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import type { MigrationSelection, SessionMigrationInput } from '../../../../shared/session-migration.js';

const uuid={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
const revision={type:'integer',minimum:1,maximum:Number.MAX_SAFE_INTEGER};
const hash={type:'string',pattern:'^[a-f0-9]{64}$'};
const selection={providerId:uuid,model:{type:'string',minLength:1,maxLength:120},effort:{type:'string',maxLength:30}};
type Params={id:string;sessionId:string};
const params={type:'object',additionalProperties:false,required:['id','sessionId'],properties:{id:uuid,sessionId:uuid}};
export function migrationRoutes(app:FastifyInstance,security:ProjectSessions,ownerType:'project'|'skill') {
  const base='/:id/sessions/:sessionId/migration';
  const owner=(id:string)=>({ownerType,ownerId:id});
  app.get<{Params:Params}>(base,{schema:{params}},async(request,reply)=>{
    security.session(request,reply);return agentHost({operation:'session_migration_status',...owner(request.params.id),sessionId:request.params.sessionId});
  });
  app.get<{Params:Params;Querystring:MigrationSelection}>(base+'/preview',{
    schema:{params,querystring:{type:'object',additionalProperties:false,required:['providerId','model','effort'],properties:selection}},
  },async(request,reply)=>{
    security.session(request,reply);return agentHost({operation:'session_migration_preview',...owner(request.params.id),sessionId:request.params.sessionId,selection:request.query});
  });
  app.post<{Params:Params;Body:SessionMigrationInput}>(base,{
    bodyLimit:4096,schema:{params,body:{type:'object',additionalProperties:false,
      required:['requestId','revision','sourceSha256','targetSha256','providerId','model','effort'],
      properties:{...selection,requestId:uuid,revision,sourceSha256:hash,targetSha256:hash}}},
  },async(request,reply)=>{
    security.mutation(request,reply);return agentHost({operation:'session_migrate',...owner(request.params.id),sessionId:request.params.sessionId,input:request.body});
  });
  app.post<{Params:Params&{requestId:string};Body:{revision:number}}>(base+'/:requestId/rollback',{
    bodyLimit:1024,schema:{params:{...params,required:[...params.required,'requestId'],properties:{...params.properties,requestId:uuid}},
      body:{type:'object',additionalProperties:false,required:['revision'],properties:{revision}}},
  },async(request,reply)=>{
    security.mutation(request,reply);return agentHost({operation:'session_migration_rollback',...owner(request.params.id),sessionId:request.params.sessionId,input:{requestId:request.params.requestId,...request.body}});
  });
}
