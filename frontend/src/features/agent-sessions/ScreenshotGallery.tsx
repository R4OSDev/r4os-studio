import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {AgentRun,SessionScreenshot} from '../../../../shared/agent-sessions';
import {busyRun,useSessionApi,sessionPath} from './api';
import {useScreenshotGallery} from './useScreenshotGallery';
import {useStoredImage} from './ReplyImage';
import './gallery.css';

function date(value:string|null) {const parsed=value?new Date(value):null;return parsed&&!Number.isNaN(parsed.valueOf())?parsed.toLocaleString():'Unknown time';}
function GalleryImage({entry,thumbnail=false,paused=false}:{entry:SessionScreenshot;thumbnail?:boolean;paused?:boolean}) {
  const [attempt,setAttempt]=useState(0);
  const {base}=useSessionApi(),endpoint=paused?null:base+sessionPath(entry.projectId,entry.sessionId)+'/screenshots/'+entry.jobId+'/'+entry.id+(attempt?'?retry='+attempt:'');
  const image=useStoredImage(endpoint),[failed,setFailed]=useState(false);
  const label='VM screenshot saved '+date(entry.createdAt);
  if(image?.failed||failed)return <span className="gallery-image-status" role={thumbnail?undefined:'status'}>{thumbnail?'Unavailable':<>The original screenshot is unavailable. <button type="button" className="gallery-image-retry" onClick={()=>{setFailed(false);setAttempt(value=>value+1);}}>Retry image</button></>}</span>;
  if(!image?.url)return <span className="gallery-image-status" aria-hidden={thumbnail||undefined} role={thumbnail?undefined:'status'}>{thumbnail?'…':'Loading screenshot…'}</span>;
  return <img src={image.url} alt={label} onError={()=>setFailed(true)}/>;
}
function ThumbnailImage({entry,paused}:{entry:SessionScreenshot;paused:boolean}) {
  const element=useRef<HTMLDivElement>(null),[visible,setVisible]=useState(false);
  useEffect(()=>{
    const target=element.current!,observer=new IntersectionObserver(entries=>setVisible(entries[0]?.isIntersecting??false),
      {root:target.closest('.gallery-thumbnails'),rootMargin:'0px 120px',threshold:0});
    observer.observe(target);return()=>observer.disconnect();
  },[]);
  return <div ref={element} className="gallery-thumbnail-media">{visible&&!paused?<GalleryImage entry={entry} thumbnail/>:<span aria-hidden="true">…</span>}</div>;
}

export function ScreenshotGallery({ownerId,sessionId,reauth,close,run,stop}:{ownerId:string;sessionId:string;reauth:()=>Promise<void>;close:()=>void;run:AgentRun|null|undefined;stop:()=>Promise<void>}) {
  const gallery=useScreenshotGallery(ownerId,sessionId,reauth),dialog=useRef<HTMLDialogElement>(null),closer=useRef<HTMLButtonElement>(null),strip=useRef<HTMLDivElement>(null),title=useId();
  const [selected,setSelected]=useState<{entry:SessionScreenshot;latest:string|null}|null>(null),[edges,setEdges]=useState({start:true,end:true});
  const [shown,setShown]=useState(!document.hidden);
  const windowKey=useRef(''),hadExtra=useRef(false);
  const anchor=useRef<{id:string;offset:number}|null>(null);
  const entry=selected?.entry??gallery.latest,following=!selected,visible=gallery.page?.available&&!gallery.authLost;
  const extra=selected&&gallery.latest?.id!==selected.latest&&!gallery.page?.items.some(value=>value.id===gallery.latest?.id)?gallery.latest:null;
  const entries=extra?[extra,...gallery.page!.items]:gallery.page?.items??[];
  useEffect(()=>{const change=()=>setShown(!document.hidden);document.addEventListener('visibilitychange',change);return()=>document.removeEventListener('visibilitychange',change);},[]);
  useEffect(()=>{const element=dialog.current!,opener=document.activeElement;element.showModal();closer.current?.focus();return()=>{element.close();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus({preventScroll:true});};},[]);
  useLayoutEffect(()=>{
    const element=strip.current;if(!element)return;
    if(windowKey.current!==gallery.windowKey){element.scrollLeft=0;windowKey.current=gallery.windowKey;}
    else if(!hadExtra.current&&extra&&anchor.current){
      const remembered=anchor.current,root=element.getBoundingClientRect();
      const previous=Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(value=>value.dataset.evidenceId===remembered.id);
      if(previous){const delta=previous.getBoundingClientRect().left-root.left-remembered.offset;if(Math.abs(delta)>1)element.scrollLeft+=delta;}
    }
    hadExtra.current=!!extra;
    const update=()=>{
      setEdges({start:element.scrollLeft<2,end:element.scrollLeft+element.clientWidth>=element.scrollWidth-2});
      const root=element.getBoundingClientRect(),first=Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(value=>value.getBoundingClientRect().right>root.left+4);
      if(first?.dataset.evidenceId)anchor.current={id:first.dataset.evidenceId,offset:first.getBoundingClientRect().left-root.left};
    };
    update();const observer=new ResizeObserver(update);observer.observe(element);element.addEventListener('scroll',update);
    return()=>{observer.disconnect();element.removeEventListener('scroll',update);};
  },[gallery.page,gallery.windowKey,extra]);
  const scroll=(direction:number)=>{
    if(direction<0&&edges.start&&gallery.hasNewer){gallery.newer();return;}
    if(direction>0&&edges.end&&gallery.page?.nextCursor){gallery.older();return;}
    strip.current?.scrollBy({left:direction*Math.max(120,strip.current.clientWidth*.8),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  };
  const newest=()=>{if(strip.current)strip.current.scrollLeft=0;setSelected(null);gallery.showLatest();};
  return createPortal(<dialog ref={dialog} className="project-dialog screenshot-gallery" aria-labelledby={title} onCancel={event=>{event.preventDefault();close();}}>
    <header className="project-dialog-header"><h2 id={title}>Screenshot gallery</h2><button ref={closer} type="button" className="project-close" aria-label="Close" onClick={close}>×</button></header>
    <div className="gallery-toolbar"><button type="button" className={following?'active':''} aria-pressed={following} onClick={newest}>Latest</button>
      <span role="status">{selected?(gallery.latest?.id!==selected.latest?'New screenshot available · viewing saved selection':'Viewing saved selection'):'Latest saved capture'}</span></div>
    {gallery.error&&<p className="project-dialog-error" role="alert">{gallery.error} <button type="button" onClick={gallery.refresh}>Retry</button></p>}
    {!gallery.page&&!gallery.error&&<p className="gallery-status" role="status">Loading screenshots…</p>}
    {gallery.page&&!gallery.page.available&&<p className="gallery-status" role="status">{gallery.page.reason??'VM screenshots are unavailable for this session.'}</p>}
    {visible&&!gallery.page!.coverage.complete&&<p className="gallery-status" role="status">Reading older saved screenshots…</p>}
    {!!gallery.page?.coverage.unqualified&&<p className="gallery-status" role="status">{gallery.page.coverage.unqualified} saved {gallery.page.coverage.unqualified===1?'capture could':'captures could'} not be linked to an original agent call.</p>}
    <div className="gallery-large">{visible&&entry?<GalleryImage key={entry.id} entry={entry} paused={!shown}/>:gallery.page?.available&&!gallery.busy&&!gallery.authLost?<p>No screenshots yet.</p>:null}</div>
    {visible&&entry&&<p className="gallery-caption">{entry.diagnosticOnly && 'Diagnostic only · Desktop content unconfirmed · '}Saved {date(entry.createdAt)} · {entry.width} × {entry.height}</p>}
    {visible&&<div className="gallery-filmstrip"><button type="button" className="gallery-scroll" aria-label="Scroll to newer screenshots" disabled={gallery.busy||edges.start&&!gallery.hasNewer} onClick={()=>scroll(-1)}>‹</button>
      <div ref={strip} className="gallery-thumbnails" role="group" aria-label="Saved screenshots" onKeyDown={event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        const buttons=Array.from(event.currentTarget.querySelectorAll('button')),i=buttons.indexOf(document.activeElement as HTMLButtonElement);
        if(i<0)return;event.preventDefault();buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,i+(event.key==='ArrowRight'?1:-1)))]?.focus();
      }}>
        {entries.map(value=><button type="button" key={value.id} data-evidence-id={value.id} className={'gallery-thumbnail'+(value.id===entry?.id?' selected':'')} aria-pressed={value.id===entry?.id}
          aria-label={'View screenshot saved '+date(value.createdAt)} onClick={()=>{if(value.id===gallery.latest?.id)newest();else{gallery.hold();setSelected({entry:value,latest:gallery.latest?.id??null});}}}>
          <ThumbnailImage entry={value} paused={!shown}/><span>{date(value.createdAt)}</span></button>)}
      </div><button type="button" className="gallery-scroll" aria-label="Scroll to older screenshots" disabled={gallery.busy||edges.end&&!gallery.page?.nextCursor} onClick={()=>scroll(1)}>›</button></div>}
    <footer className="project-actions">{busyRun(run?.state)&&<button type="button" disabled={run?.state==='stopping'} onClick={()=>void stop()}>Stop current run</button>}<button type="button" disabled={gallery.busy} onClick={gallery.refresh}>Refresh</button><button type="button" onClick={close}>Close</button></footer>
  </dialog>,document.body);
}
