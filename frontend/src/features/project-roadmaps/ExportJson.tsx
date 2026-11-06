import {useEffect,useRef,useState} from 'react';
import type {RoadmapBinding,RoadmapExport,RoadmapJsonInput} from '../../../../shared/project-roadmaps';
import {projectRequestId,ProjectRequestError} from '../projects/api';
import {roadmapRequest} from './api';

type Selection={scope:'roadmap'}|{scope:'version';versionId:string}|{scope:'subversion';versionId:string;subversionId:string};
type Recovery={pending?:RoadmapJsonInput;confirmed?:{input:RoadmapJsonInput;metadata:RoadmapExport}};
export function ExportJson({id,token,binding,selection,disabled,busyChanged}:{id:string;token:string;binding:RoadmapBinding;selection:Selection;disabled:boolean;busyChanged:(value:boolean)=>void}) {
 const key='studio.roadmap.json-export.'+id+'.'+JSON.stringify(selection);
 const [initial]=useState(()=>{
  try{
   const value=JSON.parse(sessionStorage.getItem(key)??'{}') as Recovery;
   if(!value||typeof value!=='object'||Object.keys(value).some(k=>!['pending','confirmed'].includes(k)))throw Error();
   for(const input of [value.pending,value.confirmed?.input].filter(Boolean) as RoadmapJsonInput[]){
    if(!/^[a-f0-9-]{36}$/.test(input.requestId)||!/^[a-f0-9-]{36}$/.test(input.currentVersionId)||!Number.isSafeInteger(input.expectedRevision)||input.expectedRevision<1||input.scope!==selection.scope
     ||('versionId' in selection&&(!('versionId' in input)||selection.versionId!==input.versionId))||('subversionId' in selection&&(!('subversionId' in input)||selection.subversionId!==input.subversionId)))throw Error();
   }
   if(value.confirmed&&value.confirmed.metadata.id!==value.confirmed.input.requestId)throw Error();
   return {value,error:''};
  }catch{return {value:{} as Recovery,error:'The original JSON export needs reconciliation. Browser data was preserved.'};}
 });
 const [recovery,setRecovery]=useState(initial.value),[busy,setBusy]=useState(false),[error,setError]=useState(initial.error),latch=useRef(false),alive=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{busyChanged(busy);return()=>busyChanged(false);},[busy,busyChanged]);
 async function download(){
  if(disabled||latch.current||initial.error)return;latch.current=true;setBusy(true);setError('');
  const same=recovery.confirmed?.input.expectedRevision===binding.revision&&recovery.confirmed.input.currentVersionId===binding.currentVersionId;
  const input=recovery.pending??(same?recovery.confirmed!.input:{requestId:projectRequestId(),expectedRevision:binding.revision,currentVersionId:binding.currentVersionId,...selection});
  try{
   if(input.scope!==selection.scope||JSON.stringify(Object.fromEntries(Object.entries(input).filter(([k])=>['scope','versionId','subversionId'].includes(k))))!==JSON.stringify(selection))throw Error('The original JSON export belongs to another selection. Browser data was preserved.');
   let metadata=same&&!recovery.pending?recovery.confirmed!.metadata:null;
   if(!metadata){sessionStorage.setItem(key,JSON.stringify({...recovery,pending:input}));setRecovery({...recovery,pending:input});metadata=await roadmapRequest<RoadmapExport>(id,'/json-exports',token,'POST',input);}
   const target=selection.scope==='roadmap'?metadata.roadmapId:selection.scope==='version'?selection.versionId:selection.subversionId;
   if(metadata.id!==input.requestId||metadata.projectId!==id||metadata.format!=='json'||metadata.scope!==selection.scope||metadata.targetId!==target||metadata.revision!==input.expectedRevision||metadata.currentVersionId!==input.currentVersionId||metadata.storedTreeComplete!==true||metadata.archivedTreesIncluded!==false||!Number.isSafeInteger(metadata.byteLength)||metadata.byteLength<1||!/^[a-f0-9]{64}$/.test(metadata.sha256)||!/^([0-9]+\.[0-9]+\.(X|[0-9]+)|roadmap)\.json$/.test(metadata.filename))throw Error('The original JSON snapshot metadata could not be confirmed.');
   const ready={confirmed:{input,metadata}};sessionStorage.setItem(key,JSON.stringify(ready));if(!alive.current)return;setRecovery(ready);
   const link=document.createElement('a');link.href=`/api/projects/${id}/roadmap/exports/${metadata.id}/content`;link.download=metadata.filename;document.body.append(link);try{link.click();}finally{link.remove();}
  }catch(cause){
   if(!alive.current)return;
   if([400,404,409,410,413,422].includes((cause as ProjectRequestError).status)){
    // A saved file is authoritative even if its creation reply was lost.
    try{await roadmapRequest(id,'/exports/'+input.requestId);}catch(check){if([404,410].includes((check as ProjectRequestError).status)){sessionStorage.removeItem(key);setRecovery({});}}
   }
   setError((cause as Error).message||'The original JSON export is unconfirmed. Retry the same request.');
  }finally{latch.current=false;if(alive.current)setBusy(false);}
 }
 return <div className="roadmap-export"><button type="button" disabled={disabled||busy||!!initial.error} onClick={()=>void download()} aria-label={`Download ${selection.scope} JSON`}>{busy?'Preparing JSON…':recovery.pending?'Resume JSON export':'Download JSON'}</button>{error&&<p className="project-error" role="alert">{error}</p>}</div>;
}
