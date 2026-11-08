import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {SessionContext} from '../../../../shared/agent-sessions';
import type {ContextRequestDetail,ContextRequestPage} from '../../../../shared/context-requests';
import {sessionPath,useSessionApi} from './api';
import './context-inspector.css';

const number=new Intl.NumberFormat('en-US');
const percentage=new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1});
const amount=(value:number|null|undefined)=>value==null?'Unknown':number.format(value);
const date=(value:string)=>new Date(value).toLocaleString();
const purposes:Record<string,string>={conversation:'Conversation',summary:'Summary',vision:'Vision','image-generation':'Image generation'};
const colors:Record<string,string>={free:'#66a98f',tools:'#b9a060',conversation:'#9576cf',system:'#c08b70',other:'#747089'};

export function ContextInspector({projectId,sessionId,context,close}:{projectId:string;sessionId:string;context?:SessionContext;close:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null),title=useId();
  const {request,scope}=useSessionApi();
  const [selected,setSelected]=useState<string|null>(null),[refresh,setRefresh]=useState(0);
  const [view,setView]=useState<{record:ContextRequestDetail|null;page:ContextRequestPage}|null>(null);
  const [loading,setLoading]=useState(true),[error,setError]=useState('');
  const path=sessionPath(projectId,sessionId)+'/context-requests';
  useEffect(()=>{
    const element=dialog.current!,opener=document.activeElement;element.showModal();
    return()=>{element.close();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus();};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();
    async function load(){
      try{
        const page=await request<ContextRequestPage>(path+'?limit=1','','GET',undefined,controller.signal);
        const id=selected??page.requests[0]?.id;
        const record=id?await request<ContextRequestDetail>(path+'/'+id,'','GET',undefined,controller.signal):null;
        if(!controller.signal.aborted){setView({record,page});setError('');setLoading(false);}
      }catch(failure){if(!controller.signal.aborted){setError(failure instanceof Error?failure.message:'The original request could not be read.');setLoading(false);}}
    }
    void load();return()=>controller.abort();
  },[path,request,scope,selected,refresh,context?.revision]);
  function choose(id:string|null){setLoading(true);setError('');setView(null);setSelected(id);setRefresh(value=>value+1);}
  const record=view?.record,breakdown=record?.context;
  const estimated=breakdown?.state==='estimated',capacity=breakdown?.capacity;
  const denominator=estimated?Math.max(capacity??0,breakdown.estimatedInput??0):0;
  const categories=estimated?[
    {id:'free',label:'Free',tokens:breakdown.free},
    ...['tools','conversation','system','other'].flatMap(id=>breakdown.categories.filter(row=>row.id===id)),
  ]:[];
  return createPortal(<dialog ref={dialog} className="context-inspector" aria-labelledby={title} onCancel={event=>{event.preventDefault();close();}}>
    <header className="context-inspector-header"><h2 id={title}>Context</h2>
      <nav aria-label="Request history"><button type="button" aria-label="Previous request" disabled={loading||!record?.older} onClick={()=>choose(record!.older)}>‹</button>
        <span>{record?`${record.position} of ${record.total}`:'No request'}</span>
        <button type="button" aria-label="Next request" disabled={loading||!record?.newer} onClick={()=>choose(record!.newer)}>›</button></nav>
      <button type="button" className="context-close" aria-label="Close context" onClick={close}>×</button>
    </header>
    <div className="context-inspector-scroll" aria-busy={loading}>
      {loading&&<p role="status">Loading original request…</p>}
      {error&&<div className="context-message" role="alert"><p>{error}</p><button type="button" onClick={()=>choose(selected)}>Try again</button></div>}
      {!loading&&!error&&view&&!record&&<div className="context-message"><h3>No captured request</h3><p>{view.page.notice}</p>
        <p>Requests are recorded when new direct Studio calls are dispatched.</p>
        {context&&<dl className="context-facts"><dt>Last reported context</dt><dd>{amount(context.usedTokens)}</dd><dt>Reported / configured window</dt><dd>{amount(context.capacityTokens)}</dd>
          <dt>State</dt><dd>{context.state}</dd></dl>}
      </div>}
      {record&&!error&&<>
        <div className="context-request-heading"><strong>{record.model}</strong><span>{purposes[record.purpose]??record.purpose} · {record.protocol}</span>
          <time dateTime={record.at}>{date(record.at)}</time>
          <small>{record.status==='response-received'?`Provider responded${record.httpStatus?' · HTTP '+record.httpStatus:''}`:'Dispatch attempted · provider receipt unconfirmed'} · {record.phase}</small>
        </div>
        <div className="context-inspector-body">
          <div className="context-bar-column"><span>Estimated input</span>
            <div className={'context-stack'+(!estimated?' context-stack-unknown':'')} aria-hidden="true">
              {categories.map(row=>row.tokens!=null&&row.tokens>0&&<div key={row.id} data-category={row.id} style={{height:denominator>0?`${row.tokens/denominator*100}%`:'0%',background:colors[row.id]}}>
                {denominator>0&&row.tokens/denominator>.1&&<span>{row.label}</span>}</div>)}
            </div><small>{capacity==null?'Capacity unknown':amount(capacity)+' capacity'}</small>
          </div>
          <div className="context-breakdown">
            <h3>Context breakdown <small>Estimated tokens</small></h3>
            {estimated?<dl className="context-categories">{categories.map(row=><div key={row.id} data-category={row.id}>
              <dt><i style={{background:colors[row.id]}} aria-hidden="true"/>{row.label}</dt>
              <dd>{amount(row.tokens)}<small>{row.tokens!=null&&denominator>0?percentage.format(row.tokens/denominator):'Unknown'}</small></dd>
            </div>)}</dl>:<p>{breakdown?.reason??'Component estimates are unavailable for this original request.'}</p>}
            {!!breakdown?.overflow&&<p className="context-overflow">Estimated input exceeds capacity by {amount(breakdown.overflow)} tokens. The bar is scaled to the input.</p>}
            <dl className="context-facts">
              <dt>Estimated input</dt><dd>{amount(breakdown?.estimatedInput)}</dd>
              <dt>Provider-reported input</dt><dd>{amount(record.usage.input)}</dd>
              {record.usage.cachedInput!=null&&<><dt>Cached input (included)</dt><dd>{amount(record.usage.cachedInput)}</dd></>}
              {record.usage.cacheWrite!=null&&<><dt>Cache write (included)</dt><dd>{amount(record.usage.cacheWrite)}</dd></>}
              <dt>Effective input limit</dt><dd>{amount(breakdown?.inputLimit)}</dd>
              <dt>Model window</dt><dd>{amount(breakdown?.modelWindow)}</dd>
              <dt>Output / headroom reserve</dt><dd>{amount(breakdown?.outputReserve)}</dd>
            </dl>
            <p className="context-explanation">Categories and Free use one local estimate. Provider-reported totals use provider accounting and may differ. Output is excluded.</p>
            {breakdown&&!breakdown.policyEnforced&&<p className="context-explanation">This legacy request did not use full-input limit admission. Capacity uses its recorded model window.</p>}
            <details><summary>Counting method and original</summary><p>{breakdown?.method??'Unavailable'}</p>
              <dl className="context-facts"><dt>Usage source</dt><dd>{record.usage.source}</dd><dt>Original body</dt><dd>{amount(record.bytes)} bytes</dd>
                <dt>Request</dt><dd>{record.id}</dd><dt>Provider</dt><dd>{record.providerId}</dd><dt>SHA-256</dt><dd>{record.sha256}</dd></dl>
            </details>
          </div>
        </div>
        {!record.bodyAvailable&&<p className="context-message">The complete original body is no longer retained. Recorded metadata and estimates remain available.</p>}
      </>}
    </div>
    <footer className="context-inspector-footer"><div><small>Only captured dispatch attempts are shown.</small>
      {!!view?.page.retention.droppedRequests&&<small>{amount(view.page.retention.droppedRequests)} older records expired.</small>}</div>
      <button type="button" onClick={()=>choose(null)} disabled={loading}>Latest request</button>
    </footer>
  </dialog>,document.body);
}
