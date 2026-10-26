"""V5 update tool harness: original durable job, one admission, read-only waiting."""
import asyncio
import uuid
from profile import UPDATE_TOOLS
from contracts import DevelopmentFault,UnconfirmedGuestEffect,ACTIVE

class UpdateTools:
 def __init__(self,development):self.development=development;self.worker=development.worker
 async def call(self,name,value,call_id):
  from session_store import encode
  job=None;request_id=str(uuid.uuid5(uuid.UUID(self.worker.run_id),'development:'+call_id))
  try:
   from vm_worker import broker_call
   cap=await broker_call({'operation':'capabilities'})
   if cap.get('features',{}).get('updateAgentTools')!=1:
    raise DevelopmentFault('Adopt the update-agent-capable development host before using this new session profile.',503)
   request=self.development.request
   revision=self.worker.store.project['revision']
   if name=='read_update_package':
    action=value['action'];ident=value.get('id')
    if action in ('options','updates','jobs') and ident is not None:raise DevelopmentFault('Read options/list without an object ID.',400)
    if action not in ('options','updates','jobs') and not ident:raise DevelopmentFault('Supply the confirmed plan/package/update ID.',400)
    op={'options':'update_options','updates':'update_list','jobs':'update_job_list','plan':'read_update_plan','package':'package_artifact','update':'read_update'}[action]
    result=await request(op,**({'id':ident} if ident else {}))
    if action=='options':
     result={**result,'plans':[{key:plan[key] for key in ('id','sha256','metadata','activation','priority') if key in plan} for plan in result['plans']],
      'artifacts':[{'id':item['id'],'buildId':item['buildId'],'entry':item['entry'],'kind':item['kind'],'role':item['role'],
       'updateMetadata':{key:item.get('updateMetadata',{}).get(key) for key in ('available','reason','identity','payloadKind')}} for item in result['artifacts']]}
    if action=='update':result={'update':compact_record(result['update'])}
    return {'success':True,'output':encode(result)}
   if name=='plan_update_package':
    result=await request('update_plan',input={'requestId':request_id,'projectRevision':revision,**value})
    return {'success':True,'output':encode(result)}
   body={'requestId':request_id,'projectRevision':revision}
   if name=='build_update_package':
    op='package';body.update(value)
   elif name in ('check_update_vm','upload_update_package'):
    op='update_probe' if name=='check_update_vm' else 'update_transfer';body.update(value)
   elif name=='install_update_package':
    op='update_install';body.update(value)
   elif name=='commit_update':
    op='update_commit';body.update(value)
   elif name=='verify_update':
    op='update_verify';body.update(deadlineSeconds=120,fullArtifactHashes=True);body.update(value)
   else:
    op='update_recovery';body.update(value)
    if name=='resume_update':
     body['action']='resume-batch' if body.pop('mode')=='batch' else 'resume'
    else:
     body['action']={'abort_update':'abort-batch','rollback_update':'rollback-last','cleanup_update_transport':'cleanup'}[name]
     if name!='rollback_update':body['confirmReboot']=False
   job=await request(op,input=body)
   return await self.wait(name,job,call_id,value)
  except DevelopmentFault as error:
   return {'success':False,'error':'unknown' if getattr(error,'uncertain',False) else 'unavailable',
    'output':str(error)+' Original request ID: '+request_id+'. Read existing jobs; do not replay writes.','reasonCode':getattr(error,'reason_code',None),
    **({'development':{'jobId':job['id']}} if job else {})}
 async def wait(self,name,job,call_id,arguments):
  from run_store import item
  worker=self.worker
  pending={'id':call_id,'runId':worker.run_id,'type':'tool','tool':'studio.'+name,
    'arguments':arguments,'status':'pending','development':{'jobId':job['id']}}
  worker.items[call_id]=pending;item(worker.store,worker.session_id,worker.run_id,pending)
  deadline=asyncio.get_running_loop().time()+720
  page=None
  while job['state'] in ACTIVE:
   if worker.stopping:
    return {'success':False,'error':'interrupted','output':'Update wait stopped. A native effect may remain durable; inspect its original job/update. Stop does not roll it back.','development':{'jobId':job['id']}}
   if asyncio.get_running_loop().time()>=deadline:
    raise UnconfirmedGuestEffect('The original update job remains unconfirmed. Read its saved ID; no admission or native write was repeated.')
   try:
    page=await self.development.request('wait_update',id=job['id']);job=page['job']
   except DevelopmentFault as error:
    if error.code!=503 or getattr(error,'uncertain',False):raise
    await asyncio.sleep(1)  # Only reconnect to the original read-only wait.
  if job.get('updateInstallation'):
   job={**job,'updateInstallation':compact_record(job['updateInstallation'])}
   if page:page={**page,'job':job}
  return self.development.result(job,page)

def compact_record(value):
 """Keep decisions/proof; full original diagnostics remain in the durable browser record."""
 from session_store import encode
 if len(encode(value).encode())<=131072:return value
 fields=('schema','id','projectId','jobId','sessionId','revision','phase','vmId','vmRevision','imageId','imageSha256',
  'systemGeneration','targetRelease','packageArtifactIds','transferJobIds','batchId','transactions','lastStatus','lastObservedStatus',
  'installationConfirmed','rollbackConfirmed','abortConfirmed','cleanupConfirmed','proof','error','updateEpoch')
 return {**{key:value[key] for key in fields if key in value},'diagnosticsInOriginalRecord':True}
