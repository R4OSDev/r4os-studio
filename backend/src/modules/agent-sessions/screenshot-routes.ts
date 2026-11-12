import type {FastifyInstance} from 'fastify';
import type {ProjectSessions} from '../projects/sessions.js';
import type {SessionScreenshot,ScreenshotPage} from '../../../../shared/agent-sessions.js';
import {sessionStore} from './store.js';
import {readEvidence,screenshotPayload} from '../project-development/evidence-media.js';
import {ProjectError} from '../projects/store.js';

const identity={type:'string',pattern:'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$'};
const params={type:'object',required:['id','sessionId'],additionalProperties:false,properties:{id:identity,sessionId:identity}};
type Params={id:string;sessionId:string};
export function screenshotRoutes(app:FastifyInstance,directory:string,security:ProjectSessions,providers:string|undefined,ownerType:'project'|'skill') {
  const owner=(id:string)=>ownerType==='skill'?{ownerType,ownerId:id}:{projectId:id};
  app.get<{Params:Params;Querystring:{cursor?:string;limit?:number}}>('/:id/sessions/:sessionId/screenshots',{
    schema:{params,querystring:{type:'object',additionalProperties:false,properties:{cursor:{type:'string',minLength:1,maxLength:1024},limit:{type:'integer',minimum:1,maximum:32}}}},
  },async(request,reply)=>{
    security.session(request,reply);
    return sessionStore<ScreenshotPage>(directory,{operation:'screenshots',...owner(request.params.id),sessionId:request.params.sessionId,...request.query},providers);
  });
  app.get<{Params:Params&{jobId:string;evidenceId:string};Querystring:{original?:boolean}}>('/:id/sessions/:sessionId/screenshots/:jobId/:evidenceId',{
    schema:{params:{...params,required:['id','sessionId','jobId','evidenceId'],properties:{...params.properties,jobId:identity,evidenceId:identity}},
      querystring:{type:'object',properties:{original:{type:'boolean'}}}},
  },async(request,reply)=>{
    security.session(request,reply);
    const {id,sessionId,jobId,evidenceId}=request.params;
    const member=await sessionStore<SessionScreenshot>(directory,{operation:'screenshot',...owner(id),sessionId,jobId,evidenceId},providers);
    const original=request.query.original===true;
    const image=await readEvidence({operation:'evidence',projectId:id,id:jobId,evidenceId,presentationSessionId:sessionId},original);
    const {metadata}=image,{observer,captureOrigin:origin}=metadata;
    if(metadata.kind!=='screenshot'||metadata.id!==evidenceId||metadata.jobId!==jobId||metadata.projectId!==id
      ||metadata.source!=='qmp-png'||metadata.scope!=='assigned-vm-screen'||!observer||observer.sessionId!==sessionId||observer.agentRunId!==member.runId
      ||origin!=null&&(origin.requestId!==member.requestId||origin.operation!==(member.tool==='studio.capture_vm'?'capture':'input'))
      ||metadata.sha256!==member.sha256||metadata.bytes!==member.bytes||metadata.width!==member.width||metadata.height!==member.height
      ||metadata.preview?.sha256!==member.preview?.sha256||metadata.preview?.bytes!==member.preview?.bytes
      ||metadata.preview?.mediaType!==member.preview?.mediaType||metadata.preview?.error!==member.preview?.error)
      throw new ProjectError('The original screenshot bytes or membership could not be confirmed.',409);
    const media=await screenshotPayload(image,original);
    return reply.header('Cache-Control','private, no-store').header('X-Content-Type-Options','nosniff')
      .header('Content-Disposition',`${original?'attachment':'inline'}; filename="${media.filename}"`).type(media.mediaType).send(media.data);
  });
}
