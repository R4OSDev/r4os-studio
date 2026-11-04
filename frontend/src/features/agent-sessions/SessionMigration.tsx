import { useCallback, useEffect, useState } from 'react';
import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
import type { SessionMigrationInput, SessionMigrationPreview, SessionMigrationStatus } from '../../../../shared/session-migration';
import { ProjectField } from '../projects/ProjectField';
import { projectRequestId, ProjectRequestError } from '../projects/api';
import { useSessionApi, sessionPath, busyRun } from './api';
import { availableModels, providerLabel, effortLabel } from './modelChoices';

export function SessionMigration({session,options,projectId,token,changed,busyChanged,disabled}:{
  session:AgentSession;options:SessionOptions|null;projectId:string;token:string;
  changed:(session:AgentSession)=>void;busyChanged:(busy:boolean)=>void;disabled:boolean;
}) {
  const {request}=useSessionApi(),base=sessionPath(projectId,session.id)+'/migration';
  const [status,setStatus]=useState<SessionMigrationStatus|null>(null),[preview,setPreview]=useState<SessionMigrationPreview|null>(null);
  const [providerId,setProviderId]=useState(''),[model,setModel]=useState(''),[effort,setEffort]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const key='studio.session-migration.'+session.id;
  const [pending,setPending]=useState<SessionMigrationInput|null>(()=>{try{return JSON.parse(sessionStorage.getItem(key)??'null') as SessionMigrationInput|null;}catch{return null;}});
  const providers=options?.providers.filter(p=>p.type==='api')??[],provider=providers.find(p=>p.id===providerId),models=availableModels(provider),selected=models.find(m=>m.id===model);
  useEffect(()=>{busyChanged(busy);return()=>busyChanged(false);},[busy,busyChanged]);
  const read=useCallback(async()=>{
    const value=await request<SessionMigrationStatus>(base);setStatus(value);
    if(pending&&value.migration?.requestId===pending.requestId){sessionStorage.removeItem(key);setPending(null);}
    if(value.engine!==(session.engine.kind??'codex')||value.revision!==session.revision){
      const result=await request<{session:AgentSession}>(sessionPath(projectId,session.id));changed(result.session);
    }
  },[request,base,pending,key,session.engine.kind,session.revision,session.id,projectId,changed]);
  useEffect(()=>{if(busy)return;let mounted=true;void Promise.resolve().then(()=>{if(mounted)return read();}).catch((e:Error)=>{if(mounted)setError(e.message);});return()=>{mounted=false;};},[read,busy]);
  async function review(){
    setBusy(true);setError('');setPreview(null);
    try{setPreview(await request<SessionMigrationPreview>(base+'/preview?'+new URLSearchParams({providerId,model,effort})));}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function convert(){
    const input=pending??(preview?.allowed&&preview.sourceSha256&&preview.targetSha256&&preview.target?{requestId:projectRequestId(),revision:preview.revision,sourceSha256:preview.sourceSha256,targetSha256:preview.targetSha256,...preview.target}:null);
    if(!input)return;
    setBusy(true);setError('');
    try{
      sessionStorage.setItem(key,JSON.stringify(input));setPending(input);
      const value=await request<SessionMigrationStatus>(base,token,'POST',input);setStatus(value);
      sessionStorage.removeItem(key);setPending(null);
      const result=await request<{session:AgentSession}>(sessionPath(projectId,session.id));changed(result.session);
    }catch(e){
      if(e instanceof ProjectRequestError&&e.status>=400&&e.status<500&&e.status!==408){sessionStorage.removeItem(key);setPending(null);setPreview(null);}
      setError((e as Error).message);
    }finally{setBusy(false);}
  }
  async function rollback(){
    if(!status?.migration)return;setBusy(true);setError('');
    try{
      setStatus(await request<SessionMigrationStatus>(base+'/'+status.migration.requestId+'/rollback',token,'POST',{revision:status.revision}));
      const result=await request<{session:AgentSession}>(sessionPath(projectId,session.id));changed(result.session);
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const reset=()=>setPreview(null),blocked=disabled||busy||busyRun(session.latestRun?.state);
  return <div className="agent-migration">
    <p className="agent-terminal-hint">{session.engine.kind==='studio'?'Studio manages this conversation with your selected model connection.':'Keep this conversation and continue it through a direct connection you choose.'}</p>
    {status?.migration&&<p className="agent-terminal-hint" role="status">{status.migration.state==='complete'?'Converted':'Returned to original runtime'} · {status.migration.records} context records. Original messages, files and tool receipts remain available.</p>}
    {session.engine.kind!=='studio'&&<>
      <p className="agent-terminal-hint">The selected connection determines account use and billing for future messages. Private reasoning stays with the original model. Hosted image generation and Fast Mode will be off; Studio web and selected skill services remain available when configured.</p>
      <ProjectField id="migration-provider" label="Direct connection"><select id="migration-provider" value={providerId} disabled={blocked||!!pending} onChange={e=>{setProviderId(e.target.value);setModel('');setEffort('');reset();}}><option value="">Choose a connection</option>{providers.map(p=><option value={p.id} key={p.id} disabled={!availableModels(p).length}>{providerLabel(p)}</option>)}</select></ProjectField>
      <ProjectField id="migration-model" label="Model"><select id="migration-model" value={model} disabled={blocked||!!pending||!provider} onChange={e=>{setModel(e.target.value);setEffort(models.find(m=>m.id===e.target.value)?.defaultEffort??'');reset();}}><option value="">Choose a model</option>{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></ProjectField>
      <ProjectField id="migration-effort" label="Reasoning"><select id="migration-effort" value={effort} disabled={blocked||!!pending||!selected} onChange={e=>{setEffort(e.target.value);reset();}}>{selected?.efforts.map(v=><option key={v} value={v}>{effortLabel(v,provider)}</option>)}</select></ProjectField>
      <button type="button" className="project-reload" disabled={blocked||!!pending||!selected} onClick={()=>{void review();}}>Review conversion</button>
      {preview&&<div role="status">{preview.allowed?<><p className="agent-terminal-hint">Ready: {preview.records} context records from {preview.archives} original archive files. Conversion keeps this session’s identity and starts no work. You can return before any new input or Goal command.</p><button type="button" className="project-reload project-primary" disabled={blocked||!!pending} onClick={()=>{void convert();}}>Convert this session to Studio</button></>:<ul>{preview.blockers.map((reason,index)=><li key={index}>{reason}</li>)}</ul>}</div>}
    </>}
    {pending&&<p className="agent-terminal-hint" role="status">The original conversion response is unconfirmed. Read its status before sending another request.</p>}
    {pending&&<button type="button" className="project-reload" disabled={blocked} onClick={()=>{void convert();}}>Retry original conversion</button>}
    <button type="button" className="project-reload" disabled={busy} onClick={()=>{setBusy(true);void read().catch((e:Error)=>setError(e.message)).finally(()=>setBusy(false));}}>Read conversion status</button>
    {status?.migration?.canRollback&&<button type="button" className="project-reload" disabled={blocked} onClick={()=>{void rollback();}}>Return to original runtime</button>}
    {error&&<p role="alert" className="project-dialog-error">{error}</p>}
  </div>;
}
