import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {trapDialogFocus} from './dialogFocus';
import type {ContextRequestChunk,ContextRequestDetail} from '../../../../shared/context-requests';
import {sessionPath,useSessionApi} from './api';

const number=new Intl.NumberFormat('en-US');
export function OriginalRequest({projectId,sessionId,record,close}:{projectId:string;sessionId:string;record:ContextRequestDetail;close:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null),title=useId(),{request,base}=useSessionApi();
  const [offsets,setOffsets]=useState([0]),[page,setPage]=useState<{text:string;end:number;next:number|null}|null>(null);
  const [error,setError]=useState(''),[actionError,setActionError]=useState(''),[status,setStatus]=useState('');
  const [pending,setPending]=useState<'copy'|'download'|null>(null);
  const original=useRef<Promise<ArrayBuffer>|null>(null),fullRead=useRef<AbortController|null>(null);
  const offset=offsets[offsets.length-1],path=sessionPath(projectId,sessionId)+'/context-requests/'+record.id;
  useEffect(()=>{
    const element=dialog.current!,opener=document.activeElement;element.showModal();
    return()=>{element.close();fullRead.current?.abort();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus();};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();
    void request<ContextRequestChunk>(path+'/body?offset='+offset+'&limit=65536','','GET',undefined,controller.signal)
      .then(value=>{
        if(controller.signal.aborted)return;
        if(value.requestId!==record.id||value.offset!==offset||value.bytes!==record.bytes)throw Error('The original request range changed.');
        const bytes=Uint8Array.from(atob(value.base64),character=>character.charCodeAt(0));
        // Do not replace a code point cut by the byte range with U+FFFD. The
        // following page starts at the first unconsumed original byte.
        const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes,{stream:value.nextOffset!==null});
        const end=offset+new TextEncoder().encode(text).length;
        if(end<=offset&&end<record.bytes)throw Error('The original request range is incomplete.');
        setPage({text,end,next:end<record.bytes?end:null});setError('');
      }).catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:'The original request could not be read.');});
    return()=>controller.abort();
  },[path,request,offset,record.id,record.bytes]);
  function navigate(starts:number[]){setPage(null);setError('');setOffsets(starts);}
  async function whole(){
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
  }
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
      const anchor=document.createElement('a');anchor.href=url;anchor.download='llm-request-'+record.id+'.json';anchor.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('Full original request downloaded.');
    }catch(failure){if(!fullRead.current?.signal.aborted)setActionError(failure instanceof Error?failure.message:'The request could not be downloaded.');}
    finally{setPending(null);}
  }
  return createPortal(<dialog ref={dialog} className="context-inspector request-original-dialog" aria-labelledby={title} onKeyDown={trapDialogFocus}
    onCancel={event=>{event.preventDefault();event.stopPropagation();close();}}>
    <header className="context-inspector-header"><h2 id={title}>Full request</h2><button type="button" onClick={close}>Back to context</button></header>
    <div className="request-original-meta"><strong>{record.model}</strong><span>{record.id}</span>
      <small>{number.format(record.bytes)} original UTF-8 bytes · SHA-256 {record.sha256}</small></div>
    <div className="request-original-pager" aria-label="Original request pages">
      <button type="button" disabled={offsets.length===1} onClick={()=>navigate(offsets.slice(0,-1))}>Previous page</button>
      <span>{page?`Bytes ${number.format(offset+1)}–${number.format(page.end)} of ${number.format(record.bytes)}`:'Loading page…'}</span>
      <button type="button" disabled={!page||page.next==null} onClick={()=>navigate([...offsets,page!.next!])}>Next page</button>
    </div>
    {error?<div className="context-message" role="alert"><p>{error}</p><button type="button" onClick={()=>navigate([0])}>Read again</button></div>:
      page?<pre className="request-original-content" tabIndex={0} aria-label="Original request body page">{page.text}</pre>:<p role="status" className="request-original-loading">Loading original bytes…</p>}
    <footer className="context-inspector-footer"><div><small>The body is shown in pages. Copy and download include the entire request.</small>
      {status&&<small role="status">{status}</small>}{actionError&&<small role="alert">{actionError}</small>}</div>
      <div className="context-footer-actions"><button type="button" disabled={pending!==null} onClick={()=>void copy()}>{pending==='copy'?'Copying…':'Copy full request'}</button>
        <button type="button" disabled={pending!==null} onClick={()=>void download()}>{pending==='download'?'Downloading…':'Download JSON'}</button></div></footer>
  </dialog>,document.body);
}
