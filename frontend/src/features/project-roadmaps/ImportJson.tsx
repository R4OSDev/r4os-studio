import {useCallback,useEffect,useRef,useState} from 'react';
import type {RoadmapBinding,RoadmapExport,RoadmapImportApply,RoadmapImportPreview,RoadmapImportResult} from '../../../../shared/project-roadmaps';
import {projectRequestId,ProjectRequestError} from '../projects/api';
import {roadmapRequest} from './api';

type FileTicket={id:string;name:string;sha256:string;byteLength:number};
type PreviewInput={requestId:string;expectedRevision:number;currentVersionId:string;mode:'add'|'update';target:Record<string,string>;source:{type:'export';exportId:string;sha256:string;byteLength:number};numberPolicy?:'next'|'preserve'};
type Ticket={file:FileTicket;metadata?:RoadmapExport;previewInput?:PreviewInput;preview?:RoadmapImportPreview;applyInput?:RoadmapImportApply;result?:RoadmapImportResult;applyRejected?:string};
function restore(key:string):Ticket|null{
 const raw=sessionStorage.getItem(key);if(!raw)return null;const value=JSON.parse(raw) as Ticket;
 if(!value?.file||!/^[a-f0-9-]{36}$/.test(value.file.id)||!/^[a-f0-9]{64}$/.test(value.file.sha256)||!Number.isSafeInteger(value.file.byteLength)||value.file.byteLength<1||value.file.byteLength>16*1024*1024)throw Error('The original JSON import needs reconciliation. Browser data was preserved.');
 if(value.previewInput&&value.previewInput.source.exportId!==value.file.id||value.preview&&value.preview.previewId!==value.previewInput?.requestId||value.applyInput&&value.applyInput.previewId!==value.preview?.previewId)throw Error('The original JSON import binding is unavailable. Browser data was preserved.');
 return value;
}
function fileHash(bytes:ArrayBuffer):Promise<string>{return new Promise((resolve,reject)=>{
 const worker=new Worker(new URL('./json-hash.worker.ts',import.meta.url),{type:'module'}),timer=setTimeout(()=>{worker.terminate();reject(Error('The JSON file hash did not finish. No upload was sent.'));},30000);
 const stop=()=>{clearTimeout(timer);worker.terminate();};worker.onmessage=event=>{stop();if(/^[a-f0-9]{64}$/.test(event.data))resolve(event.data);else reject(Error('The JSON file hash was not confirmed.'));};worker.onerror=()=>{stop();reject(Error('The JSON file could not be hashed. No upload was sent.'));};worker.postMessage(bytes);
});}

export function ImportJson({id,token,binding,rootId,versionId,disabled,busyChanged,changed}:{id:string;token:string;binding:RoadmapBinding;rootId:string;versionId:string;disabled:boolean;busyChanged:(value:boolean)=>void;changed:()=>void}){
 const key='studio.roadmap.json-import.'+id;
 const [initial]=useState(()=>{try{return {ticket:restore(key),error:''};}catch(cause){return {ticket:null,error:(cause as Error).message};}});
 const [ticket,setTicket]=useState(initial.ticket),[error,setError]=useState(initial.error),[busy,setBusy]=useState(false),[epoch,setEpoch]=useState(0),[missing,setMissing]=useState(''),[mode,setMode]=useState<'add'|'update'>('add'),[nextNumber,setNextNumber]=useState(false),[reviewed,setReviewed]=useState(false);
 const latch=useRef(false),alive=useRef(false);
 const save=useCallback((value:Ticket|null)=>{if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key);setTicket(value);},[key]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{busyChanged(busy);return()=>busyChanged(false);},[busy,busyChanged]);
 useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(busy||ticket?.applyInput&&!ticket.result)e.preventDefault();};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[busy,ticket]);
 useEffect(()=>{
  let live=true;
  void(async()=>{
   await Promise.resolve();if(!live)return;
   let value:Ticket|null;
   try{value=restore(key);}catch(cause){setError((cause as Error).message);return;}
   if(!value||initial.error)return;
   setBusy(true);setMissing('');
   try{
    if(value!.applyInput&&!value!.result&&!value!.applyRejected){const result=await roadmapRequest<RoadmapImportResult>(id,'/json-imports/requests/'+value!.applyInput.requestId);if(live){save({...value!,result});setError('');changed();}}
    else if(value!.previewInput&&!value!.preview){const preview=await roadmapRequest<RoadmapImportPreview>(id,'/json-imports/previews/'+value!.previewInput.requestId);if(live){save({...value!,preview});setError('');}}
    else if(!value!.metadata){const metadata=await roadmapRequest<RoadmapExport>(id,'/json-imports/files/'+value!.file.id);if(metadata.sha256!==value!.file.sha256||metadata.byteLength!==value!.file.byteLength)throw Error('Original JSON file identity changed.');if(live){save({...value!,metadata});setError('');}}
   }catch(cause){if(live){const status=(cause as ProjectRequestError).status;setMissing([404,410].includes(status)?value!.applyInput?'apply':value!.previewInput?'preview':'file':'');setError((cause as Error).message);}}
   finally{if(live)setBusy(false);}
  })();return()=>{live=false;};
 },[id,key,epoch,save,initial.error,changed]);
 async function choose(file:File){
  if(latch.current||disabled||initial.error)return;latch.current=true;setBusy(true);setError('');
  try{
   if(!file.size||file.size>16*1024*1024)throw Error('Select one complete JSON file up to 16 MiB.');
   const bytes=await file.arrayBuffer(),sha256=await fileHash(bytes);
   const original=ticket&&!ticket.metadata?ticket.file:null;
   if(original&&(original.sha256!==sha256||original.byteLength!==bytes.byteLength))throw Error('Reselect the exact original JSON file, or discard this unused upload first.');
   const selected=original??{id:projectRequestId(),name:file.name,sha256,byteLength:bytes.byteLength};const value:Ticket={file:selected};save(value);
   const response=await fetch(`/api/projects/${id}/roadmap/json-imports/files/${selected.id}`,{method:'POST',headers:{'Content-Type':'application/octet-stream','x-csrf-token':token},body:bytes});const result=await response.json();if(!response.ok)throw new ProjectRequestError(result.message??'The original upload was not confirmed.',response.status);
   if(result.id!==selected.id||result.sha256!==sha256||result.byteLength!==selected.byteLength||result.format!=='json')throw Error('The original file receipt could not be confirmed.');save({...value,metadata:result});setMissing('');
  }catch(cause){setError((cause as Error).message);setEpoch(n=>n+1);}finally{latch.current=false;if(alive.current)setBusy(false);}
 }
 async function preview(original?:PreviewInput){
  if(!ticket?.metadata||latch.current||disabled)return;latch.current=true;setBusy(true);setError('');setReviewed(false);
  const scope=ticket.metadata.scope!;const target:Record<string,string>=scope==='roadmap'?{kind:scope,id:rootId}:scope==='version'?{kind:scope}:{kind:scope,versionId};
  const input=original??{requestId:projectRequestId(),expectedRevision:binding.revision,currentVersionId:binding.currentVersionId,mode,target,source:{type:'export' as const,exportId:ticket.file.id,sha256:ticket.file.sha256,byteLength:ticket.file.byteLength},...(scope==='subversion'&&mode==='add'?{numberPolicy:nextNumber?'next' as const:'preserve' as const}:{})};
  const value={...ticket,previewInput:input};
  try{save(value);const result=await roadmapRequest<RoadmapImportPreview>(id,'/json-imports/previews',token,'POST',input);if(result.previewId!==input.requestId||result.projectId!==id||result.source.id!==ticket.file.id||result.source.sha256!==ticket.file.sha256)throw Error('The original preview binding could not be confirmed.');save({...value,preview:result});setMissing('');}
  catch(cause){setError((cause as Error).message);setEpoch(n=>n+1);}finally{latch.current=false;if(alive.current)setBusy(false);}
 }
 async function apply(original?:RoadmapImportApply){
  if(!ticket?.preview||latch.current||disabled||!original&&!reviewed)return;latch.current=true;setBusy(true);setError('');
  const p=ticket.preview,input=original??{requestId:projectRequestId(),previewId:p.previewId,previewSha256:p.sha256,expectedRevision:p.revision,currentVersionId:p.currentVersionId,confirm:true as const};const value={...ticket,applyInput:input};
  try{save(value);const result=await roadmapRequest<RoadmapImportResult>(id,'/json-imports/apply',token,'POST',input);if(result.requestId!==input.requestId||result.previewId!==input.previewId||result.confirmed!==true)throw Error('The original import result was not confirmed.');save({...value,result});setMissing('');changed();}
  catch(cause){setError((cause as Error).message);if([400,404,409,410,413,422].includes((cause as ProjectRequestError).status))save({...value,applyRejected:(cause as Error).message});else setEpoch(n=>n+1);}finally{latch.current=false;if(alive.current)setBusy(false);}
 }
 const p=ticket?.preview,stale=!!p&&(p.revision!==binding.revision||p.currentVersionId!==binding.currentVersionId);
 return <details className="roadmap-card roadmap-json-import"><summary>Import JSON</summary>
  <p>Upload a complete subversion, version or roadmap JSON file (up to 16 MiB). Review the bound preview before applying. Existing entries omitted from the file are retained; current selection and historical archives are retained.</p>
  {!initial.error&&!ticket?.metadata&&!ticket?.applyInput&&<label>JSON file<input type="file" accept=".json,application/json" disabled={disabled||busy} onChange={e=>{const file=e.target.files?.[0];if(file)void choose(file);}}/></label>}
  {ticket&&<p>Original file: {ticket.file.name} · {ticket.file.byteLength.toLocaleString('en-US')} bytes<br/><code>{ticket.file.sha256}</code></p>}
  {ticket?.metadata&&!ticket.previewInput&&<>
   <p>Scope: {ticket.metadata.scope}. Subversions target main version <code>{versionId}</code>; version imports match version numbers within this roadmap.</p>
   <label>Mode<select value={mode} disabled={disabled||busy} onChange={e=>setMode(e.target.value as 'add'|'update')}><option value="add">Add entries</option><option value="update">Update matching numbers and child positions</option></select></label>
   {ticket.metadata.scope==='subversion'&&mode==='add'&&<label><input type="checkbox" checked={nextNumber} disabled={disabled||busy} onChange={e=>setNextNumber(e.target.checked)}/> Use next available subversion number</label>}
   <button type="button" disabled={disabled||busy} onClick={()=>void preview()}>Prepare preview</button>
  </>}
  {p&&<div className="roadmap-import-preview" aria-label="Import preview">
   <h4>Preview: {p.scope} · {p.mode}</h4><p>{p.counts.create} additions · {p.counts.update} updates · 0 deletions</p><p>{p.matching}</p>
   <p>Revision {p.revision} · Plan SHA-256 <code>{p.sha256}</code></p>
   <p><a href={`/api/projects/${id}/roadmap/exports/${ticket!.file.id}/content`} download>Read original JSON</a> · <a href={`/api/projects/${id}/roadmap/json-imports/previews/${p.previewId}/content`} download>Download complete preview and mapping</a></p>
   <ul>{p.mapping.map((m,i)=><li key={i}>{m.action} {m.kind}: <code>{m.sourceId}</code> → <code>{m.targetId}</code>{m.sourceNumber&&<> · {m.sourceNumber} → {m.targetNumber}{m.previousNumber&&<> (was {m.previousNumber})</>}</>}{m.sourceOrder!==undefined&&<> · position {m.sourceOrder} → {m.targetOrder}</>}</li>)}</ul>
   {p.detailsTruncated&&<p>The list is a preview. All {p.totalChanges} changes and before/after fields are in the complete downloadable plan.</p>}
   {p.archiveReferencesIgnored>0&&<p>{p.archiveReferencesIgnored} historical archive references remain provenance only; archived trees are not restored.</p>}
   {p.conflictCount>0&&<><p role="alert">{p.conflictCount} conflicts prevent applying:</p><ul>{p.conflicts.map((c,i)=><li key={i}>{c}</li>)}</ul></>}
   {stale&&!ticket?.result&&<p role="alert">The roadmap changed. Discard this preview, refresh the roadmap and prepare a fresh preview.</p>}
   {!ticket?.applyInput&&!ticket?.result&&p.canApply&&!stale&&<><label><input type="checkbox" checked={reviewed} disabled={disabled||busy} onChange={e=>setReviewed(e.target.checked)}/> I reviewed this preview and its target mapping</label><button type="button" className="roadmap-primary" disabled={disabled||busy||!reviewed} onClick={()=>void apply()}>Apply {p.totalChanges} changes</button></>}
  </div>}
  {ticket?.result&&<p role="status">Import confirmed at revision {ticket.result.revision}. {ticket.result.counts.create} additions and {ticket.result.counts.update} updates.</p>}
  {error&&<p role="alert" className="project-error">{error}</p>}
  {busy&&<p role="status">Reading the original JSON operation…</p>}
  {ticket&&!ticket.result&&<button type="button" disabled={busy} onClick={()=>setEpoch(n=>n+1)}>Check original operation</button>}
  {missing==='file'&&<p>Reselect the original file to retry its upload.</p>}
  {missing==='preview'&&ticket?.previewInput&&<button type="button" disabled={disabled||busy} onClick={()=>void preview(ticket.previewInput)}>Retry original preview</button>}
  {missing==='apply'&&ticket?.applyInput&&!ticket.applyRejected&&<button type="button" disabled={disabled||busy} onClick={()=>void apply(ticket.applyInput)}>Retry original import</button>}
  {ticket&&(!ticket.applyInput||ticket.result||ticket.applyRejected)&&<button type="button" disabled={busy} onClick={()=>{save(null);setError('');setMissing('');setReviewed(false);}}>Discard import selection</button>}
 </details>;
}
