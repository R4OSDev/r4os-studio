import {useCallback,useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {SkillDeletionInput,SkillDeletionPreview,SkillDeletionReceipt} from '../../../../shared/skills';
import {projectRequestId} from '../projects/api';
import {request,SkillError} from './api';
import {clearEnvironmentNoteRequests} from '../agent-sessions/environmentNoteStorage';
const prefix='studio.skill.deletion.';
type Pending={input:SkillDeletionInput;sessionIds:string[]};
export function pendingSkillDeletion(selectedId:string|null){try{if(selectedId && sessionStorage.getItem(prefix+selectedId))return selectedId;for(let i=0;i<sessionStorage.length;i++){const key=sessionStorage.key(i);if(key?.startsWith(prefix))return key.slice(prefix.length);}}catch{/* Receipt reads remain available after refresh. */}return null;}
function restored(id:string):Pending|null{try{const value=JSON.parse(sessionStorage.getItem(prefix+id)??'null');return value?.input?.requestId && Array.isArray(value.sessionIds)?value:null;}catch{return null;}}
export function DeleteSkillDialog({id,token,reauth,close,deleted}:{id:string;token:string;reauth:()=>Promise<void>;close:()=>void;deleted:(id:string)=>Promise<void>}){
 const dialog=useRef<HTMLDialogElement>(null),field=useRef<HTMLInputElement>(null),finished=useRef(false);
 const [preview,setPreview]=useState<SkillDeletionPreview|null>(null),[name,setName]=useState(''),[error,setError]=useState('');
 const [pending,setPending]=useState<Pending|null>(()=>restored(id)),[receipt,setReceipt]=useState<SkillDeletionReceipt|null>(null),[posting,setPosting]=useState(false),[epoch,setEpoch]=useState(0);
 useEffect(()=>{const element=dialog.current!,opener=document.activeElement;element.showModal();field.current?.focus();return()=>{element.close();if(opener instanceof HTMLElement && opener.isConnected)opener.focus();else document.querySelector<HTMLElement>('main[aria-label="Tools content"]')?.focus();};},[]);
 useEffect(()=>{if(preview && !pending)field.current?.focus();},[preview,pending]);
 useEffect(()=>{if(pending)return;let cancelled=false;void request<SkillDeletionPreview>('GET','/'+id+'/deletion').then(value=>{if(!cancelled){setPreview(value);}}).catch((error:SkillError)=>{if(!cancelled){setError(error.message);if(error.status===403)void reauth();}});return()=>{cancelled=true;};},[id,pending,epoch,reauth]);
 const accept=useCallback(async(value:SkillDeletionReceipt)=>{
  if(value.id!==id || value.requestId!==pending?.input.requestId)throw Error('The deletion receipt belongs to another original request.');
  setReceipt(value);
  if(value.state==='deleted')clearEnvironmentNoteRequests('skill',id);
  if(value.state==='deleted' && !finished.current){finished.current=true;sessionStorage.removeItem(prefix+id);const prefixes=[`studio.goal.skill.${id}.`,`studio.attachments.skill.${id}.`,`studio.notes.skill.${id}.`,`studio.skill.session.create.${id}`,...(pending?.sessionIds??[]).flatMap(sid=>[`studio.skill.session.run.${sid}`,`studio.skill.session.draft.${sid}`,`studio.skill.queue-control.${sid}`])];for(let n=sessionStorage.length-1;n>=0;n--){const key=sessionStorage.key(n);if(key && prefixes.some(prefix=>key===prefix || key.startsWith(prefix.endsWith('.')?prefix:prefix+'.')))sessionStorage.removeItem(key);}await deleted(id);close();}
  else if(value.state==='unknown')setError(value.reason??'Cleanup is unconfirmed. Check the original receipt or retry the same request.');
 },[id,pending,deleted,close]);
 useEffect(()=>{if(!pending || posting)return;let cancelled=false,timer:number|undefined,attempts=0;
  const read=async()=>{try{const value=await request<SkillDeletionReceipt>('GET','/'+id+'/deletion/'+pending.input.requestId);if(cancelled)return;await accept(value);if(value.state!=='deleting')return;}catch(error){if(cancelled)return;const issue=error as SkillError;setError(issue.status===404?'No original receipt was found. Retry this same request explicitly.':issue.message);if(issue.status===403)await reauth();if(++attempts>=8)return;}
   if(!cancelled)timer=window.setTimeout(()=>void read(),750);
  };void read();return()=>{cancelled=true;window.clearTimeout(timer);};
 },[id,pending,posting,accept,reauth,epoch]);
 async function submit(original?:Pending){
  if(posting)return;
  const command=original??(preview?{input:{requestId:projectRequestId(),revision:preview.revision,scopeHash:preview.scopeHash,confirmName:name},sessionIds:preview.sessionIds??[]}:null);
  if(!command)return;
  try{sessionStorage.setItem(prefix+id,JSON.stringify(command));}catch{setError('Enable session storage before deleting a skill.');return;}
  setPending(command);setPosting(true);setError('');
  try{const value=await request<SkillDeletionReceipt>('POST','/'+id+'/deletion',command.input,token);setReceipt(value);setEpoch(n=>n+1);}
  catch(error){const issue=error as SkillError;setError(issue.message);if(issue.status===403)await reauth();if(issue.status>=400 && issue.status<500){sessionStorage.removeItem(prefix+id);setPending(null);setName('');setEpoch(n=>n+1);}}
  finally{setPosting(false);}
 }
 return createPortal(<dialog ref={dialog} className="project-dialog skill-delete-dialog" aria-labelledby="delete-skill-title" onCancel={event=>{event.preventDefault();if(!posting)close();}}>
  <header className="project-dialog-header"><h2 id="delete-skill-title">Delete skill</h2></header>
  <div className="skill-delete-content"><p>Permanently delete <strong>{preview?.name??'this skill'}</strong> and its complete private data.</p><p className="skill-delete-id">Skill ID: {id}</p>
   <p>This removes its draft, scripts, references, assets, published revisions and all Skill Manager sessions, including native history, Goals, attachments, images and environment notes. Unsaved edits to this skill are discarded. Other skills and project copies remain.</p>
   {preview && <p>{preview.files} draft files · {preview.revisions} published revisions · {preview.sessions} sessions</p>}
   {preview && !preview.allowed && <div role="status"><p>Finish or stop this work using its normal controls, then check again:</p><ul>{preview.blockers.map((blocker,index)=><li key={index}>{blocker.reason}{blocker.ownerId && <span> Owner {blocker.ownerId}{blocker.sessionId?' · Session '+blocker.sessionId:''}{blocker.sessionId && <a href={blocker.ownerType==='project'?`#projects/${blocker.ownerId}/sessions/${blocker.sessionId}`:`#tools/skills/${blocker.ownerId}/sessions/${blocker.sessionId}`} onClick={close}> Open session</a>}</span>}</li>)}</ul></div>}
   {!pending && <label>Type the skill name to confirm<input ref={field} value={name} maxLength={120} autoComplete="off" disabled={!preview || !preview.allowed || posting} onChange={event=>setName(event.target.value)}/></label>}
   {pending && <p role="status">{receipt?.state==='unknown'?'Deletion unconfirmed.':receipt?.state==='deleted'?'Deleted.':'Deleting… Checking the original receipt.'}</p>}
   {error && <p className="project-dialog-error" role="alert">{error}</p>}
  </div><footer className="project-actions"><button type="button" disabled={posting} onClick={close}>{pending?'Close':'Cancel'}</button><button type="button" disabled={posting} onClick={()=>{setError('');setEpoch(n=>n+1);if(!pending)setName('');}}>Check again</button>
   {pending?<button type="button" disabled={posting} onClick={()=>void submit(pending)}>Retry same request</button>:<button type="button" className="skill-delete-action" disabled={posting || !preview?.allowed || name!==preview.name} onClick={()=>void submit()}>Delete skill</button>}
  </footer>
 </dialog>,document.body);
}
