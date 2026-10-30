import {useId,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {SessionContext} from '../../../../shared/agent-sessions';
import './context.css';

const integer=new Intl.NumberFormat('en-US');
const percent=new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:4});
const tokens=(n:number|null|undefined)=>n==null?'Unknown':integer.format(n);

export function ContextIndicator({context}:{context?:SessionContext}) {
  const id=useId(),anchor=useRef<HTMLButtonElement>(null),tooltip=useRef<HTMLDivElement>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [open,setOpen]=useState(false),[position,setPosition]=useState({left:12,top:12});
  const known=context?.state==='available' && typeof context.usedRatio==='number' && Number.isFinite(context.usedRatio)
    && context.usedRatio>=0 && typeof context.capacityTokens==='number' && context.capacityTokens>0;
  const ratio=known?context.usedRatio!:0,fill=Math.min(1,ratio),pulse=known&&ratio>.5;
  const state=context?.state??'unavailable';
  const value=known?Math.round(fill*100)+'%':'—';
  const label='Context usage: '+(known?percent.format(ratio):state)+'. Show details';
  const cancel=()=>{if(timer.current!==null)clearTimeout(timer.current);timer.current=null;};
  const show=()=>{cancel();setOpen(true);};
  const leave=()=>{cancel();timer.current=setTimeout(()=>{if(document.activeElement!==anchor.current)setOpen(false);},140);};
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{
      const r=anchor.current?.getBoundingClientRect(),t=tooltip.current?.getBoundingClientRect();
      if(!r||!t)return;
      const left=Math.max(12,Math.min(innerWidth-t.width-12,r.right-t.width));
      const above=r.top-t.height-10;
      setPosition({left,top:Math.max(12,Math.min(innerHeight-t.height-12,above>=12?above:r.bottom+10))});
    };
    const outside=(event:PointerEvent)=>{if(event.target instanceof Node&&!anchor.current?.contains(event.target)&&!tooltip.current?.contains(event.target))setOpen(false);};
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);window.addEventListener('pointerdown',outside);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);window.removeEventListener('pointerdown',outside);};
  },[open,context]);
  useLayoutEffect(()=>()=>{if(timer.current!==null)clearTimeout(timer.current);},[]);
  const close=()=>{cancel();setOpen(false);};
  const date=context?.reportedAt?new Date(context.reportedAt):null;
  return <div className="agent-context-control">
    <span className="agent-context-label">Context</span>
    <button ref={anchor} type="button" className={'agent-context'+(pulse?' pulse':'')+(!known?' unknown':'')}
      data-state={state} aria-label={label} aria-describedby={open?id:undefined} aria-expanded={open}
      onPointerEnter={show} onPointerLeave={leave} onFocus={show} onBlur={close}
      onClick={show} onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();close();}}}>
      <svg viewBox="0 0 52 34" aria-hidden="true">
        <path className="context-track" d="M4 26 A22 22 0 0 1 48 26"/>
        {known&&<><path className="context-fill" d="M4 26 A22 22 0 0 1 48 26" pathLength="100" strokeDasharray={`${fill*100} 100`}/>
          <path className="context-needle" d="M26 26 L26 10" transform={`rotate(${-90+fill*180} 26 26)`}/><circle className="context-hub" cx="26" cy="26" r="2.5"/></>}
      </svg><span aria-hidden="true">{value}</span>
    </button>
    {known&&<span className="agent-context-meter" role="meter" aria-label="Context usage" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={fill*100} aria-valuetext={percent.format(ratio)+' of the reported effective context window'}/>}
    {open&&createPortal(<div ref={tooltip} id={id} role="tooltip" className="agent-context-tooltip" style={position}
      onPointerEnter={show} onPointerLeave={leave}>
      <strong>Context usage{known?' · '+percent.format(ratio):''}</strong>
      <p className="context-state">{state!=='available'&&state[0].toUpperCase()+state.slice(1)+' · '}{context?.reason??'No qualified context measurement is available.'}</p>
      <dl><dt>Used tokens</dt><dd>{tokens(context?.usedTokens)}</dd>
        <dt>Effective window</dt><dd>{tokens(context?.capacityTokens)}</dd>
        <dt>Remaining tokens</dt><dd>{tokens(context?.remainingTokens)}</dd>
        {known&&<><dt>Remaining</dt><dd>{percent.format(Math.max(0,1-ratio))}</dd></>}
        {!!context?.overflowTokens&&<><dt>Reported overflow</dt><dd>{tokens(context.overflowTokens)}</dd></>}
        <dt>Model</dt><dd>{context?.model??'Unknown'}</dd>
        <dt>Last reported</dt><dd>{date&&!Number.isNaN(date.valueOf())?<time dateTime={context!.reportedAt!}>{date.toLocaleString()}</time>:'Unknown'}</dd>
        <dt>Source</dt><dd>{context?.source?'Native '+(context.engine==='codex'?'Codex ':'Claude ')+context.engineVersion+' · last context':'Unavailable'}</dd></dl>
      <p>Full reported context. No estimate from cumulative usage or subscription limits.</p>
    </div>,document.body)}
  </div>;
}
