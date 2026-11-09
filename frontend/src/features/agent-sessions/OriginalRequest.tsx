import {lazy,Suspense,useCallback,useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {trapDialogFocus} from './dialogFocus';
import type {ContextRequestDetail} from '../../../../shared/context-requests';
import {sessionPath,useSessionApi} from './api';

const RequestDocument=lazy(async()=>({default:(await import('./RequestDocument')).RequestDocument}));

const number=new Intl.NumberFormat('en-US');
export function OriginalRequest({projectId,sessionId,record,close}:{projectId:string;sessionId:string;record:ContextRequestDetail;close:()=>void}) {
  const prepared=record.status==='blocked-before-send';
  const dialog=useRef<HTMLDialogElement>(null),title=useId(),{base}=useSessionApi();
  const [formatted,setFormatted]=useState<{text:string;notice:string|null}|null>(null),[retry,setRetry]=useState(0);
  const [error,setError]=useState(''),[actionError,setActionError]=useState(''),[status,setStatus]=useState('');
  const [pending,setPending]=useState<'copy'|'download'|null>(null);
  const original=useRef<Promise<ArrayBuffer>|null>(null),fullRead=useRef<AbortController|null>(null);
  const path=sessionPath(projectId,sessionId)+'/context-requests/'+record.id;
  useEffect(()=>{
    const element=dialog.current!,opener=document.activeElement;element.showModal();
    return()=>{element.close();fullRead.current?.abort();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus();};
  },[]);
  const whole=useCallback(async()=>{
    if(!original.current){
      const controller=new AbortController();fullRead.current=controller;
      original.current=fetch(base+path+'/download',{cache:'no-store',signal:controller.signal}).then(async response=>{
        if(!response.ok){const failure=await response.json().catch(()=>null);throw Error(failure?.message??'The complete original request is unavailable.');}
        const bytes=await response.arrayBuffer();
        if(bytes.byteLength!==record.bytes)throw Error('The complete original request length changed.');
        return bytes;
      });
    }
    try{return await original.current;}catch(failure){original.current=null;throw failure;}
  },[base,path,record.bytes]);
  useEffect(()=>{
    let active=true;let worker:Worker|null=null,timer:ReturnType<typeof setTimeout>|undefined;
    const stop=()=>{worker?.terminate();if(timer)clearTimeout(timer);};
    void whole().then(bytes=>{
      if(!active)return;
      const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
      worker=new Worker(new URL('./request-format.worker.ts',import.meta.url),{type:'module'});
      worker.onmessage=event=>{if(active){setFormatted(event.data);setError('');}stop();};
      worker.onerror=()=>{if(active)setError('The formatted request could not be prepared.');stop();};
      timer=setTimeout(()=>{if(active)setError('The formatted request took too long to prepare.');stop();},15000);
      worker.postMessage(text);
    }).catch(failure=>{if(active)setError(failure instanceof Error?failure.message:'The original request could not be read.');});
    return()=>{active=false;stop();};
  },[retry,whole]);
  function readAgain(){setFormatted(null);setError('');setRetry(value=>value+1);}
  async function copy(){
    setPending('copy');setStatus('');setActionError('');
    try{
      const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await whole());
      let copied=false;
      if(navigator.clipboard){try{await navigator.clipboard.writeText(text);copied=true;}catch{/* HTTP LAN origins can use the focused selection fallback. */}}
      if(!copied){
        const input=document.createElement('textarea'),opener=document.activeElement;
        input.value=text;input.readOnly=true;input.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;opacity:0';
        dialog.current?.append(input);
        try{input.focus();input.select();copied=document.execCommand('copy');}
        finally{input.remove();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus();}
      }
      if(!copied)throw Error('Copy is unavailable in this browser. Download the original request instead.');
      setStatus('Full request copied.');
    }catch(failure){if(!fullRead.current?.signal.aborted)setActionError(failure instanceof Error?failure.message:'The request could not be copied.');}
    finally{setPending(null);}
  }
  async function download(){
    setPending('download');setStatus('');setActionError('');
    try{
      const url=URL.createObjectURL(new Blob([await whole()],{type:'application/json;charset=utf-8'}));
      const anchor=document.createElement('a');anchor.href=url;anchor.download=(prepared?'prepared-request-':'llm-request-')+record.id+'.json';anchor.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('Full original request downloaded.');
    }catch(failure){if(!fullRead.current?.signal.aborted)setActionError(failure instanceof Error?failure.message:'The request could not be downloaded.');}
    finally{setPending(null);}
  }
  return createPortal(<dialog ref={dialog} className="context-inspector request-original-dialog" aria-labelledby={title} onKeyDown={trapDialogFocus}
    onCancel={event=>{event.preventDefault();event.stopPropagation();close();}}>
    <header className="context-inspector-header"><h2 id={title}>{prepared?'Prepared request · not sent':'Full request'}</h2><button type="button" onClick={close}>Back to context</button></header>
    <div className="request-original-meta"><strong>{record.model}</strong><span>{record.id}</span>
      <small>{number.format(record.bytes)} original UTF-8 bytes · SHA-256 {record.sha256}</small></div>
    {error?<div className="context-message" role="alert"><p>{error}</p><button type="button" onClick={readAgain}>Read again</button></div>:
      formatted?<Suspense fallback={<p role="status" className="request-original-loading">Opening formatted request…</p>}><RequestDocument text={formatted.text}/></Suspense>:
        <p role="status" className="request-original-loading">Loading and formatting the complete request…</p>}
    <footer className="context-inspector-footer"><div><small>Formatted view with text line breaks. Copy and download preserve the complete original JSON.</small>
      {formatted?.notice&&<small>{formatted.notice}</small>}
      {status&&<small role="status">{status}</small>}{actionError&&<small role="alert">{actionError}</small>}</div>
      <div className="context-footer-actions"><button type="button" disabled={pending!==null} onClick={()=>void copy()}>{pending==='copy'?'Copying…':'Copy full request'}</button>
        <button type="button" disabled={pending!==null} onClick={()=>void download()}>{pending==='download'?'Downloading…':'Download JSON'}</button></div></footer>
  </dialog>,document.body);
}
