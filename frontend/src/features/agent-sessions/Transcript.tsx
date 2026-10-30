/** @jsxRuntime automatic */
import { Children, createContext, isValidElement, memo, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {flushSync} from 'react-dom';
import type { ReactNode } from 'react';
import Markdown, { defaultUrlTransform } from 'react-markdown';
import type { Components } from 'react-markdown';
import type { UrlTransform } from 'react-markdown';
import { ReplyImage, replyImageReference } from './ReplyImage';
import { GeneratedPreview, generatedReference } from './GeneratedImage';
import { useSessionApi } from './api';
import {StreamContext,StreamLeaf,streamTextPlugin} from './StreamText';
import {TextStream} from './textStream';

// Render a text transcript, never a live terminal. In particular OSC 52 must
// never alter the browser clipboard or survive a user copying visible output.
/* eslint-disable no-control-regex -- This function deliberately removes ANSI and C0/C1 control bytes. */
export function transcriptText(value: string) {
  return value
    .replace(/(?:\u001b\]|\u009d)[\s\S]*?(?:\u0007|\u001b\\|\u009c|$)/g, '')
    .replace(/(?:\u001b\[|\u009b)[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\u001b[ -/]*[@-Z\\-_]/g, '')
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/g, '');
}

/* eslint-enable no-control-regex */

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch { /* HTTP LAN / browser policy: use the user gesture fallback. */ }
  }
  const active = document.activeElement;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
  const input = document.createElement('textarea');
  input.value = text; input.readOnly = true; input.tabIndex = -1;
  input.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0';
  document.body.append(input); input.select();
  try { if (!document.execCommand('copy')) throw new Error('Copy failed.'); }
  finally {
    input.remove();
    if (active instanceof HTMLElement && active.isConnected) active.focus({ preventScroll: true });
    if (selection) { selection.removeAllRanges(); for (const range of ranges) selection.addRange(range); }
  }
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [feedback, setFeedback] = useState({ text: '', state: '' });
  const message = feedback.text === text ? feedback.state : '';
  return <button className="agent-copy" type="button" aria-label={label} onClick={() => {
    void copyText(text).then(() => setFeedback({ text, state: 'Copied' })).catch(() => setFeedback({ text, state: 'Copy failed' }));
  }}><span aria-live="polite">{message || 'Copy'}</span></button>;
}

export function CodeBlock({ text, label = 'Copy code', language = '' }: { text: string; label?: string; language?: string }) {
  const visible = transcriptText(text);
  return <div className="agent-code-block"><div className="agent-code-bar"><span>{language}</span><CopyButton text={visible} label={label} /></div><pre><code><StreamLeaf text={visible}/></code></pre></div>;
}

const imageScope = createContext<{ projectId: string; sessionId: string } | null>(null);
function MarkdownImage({ src, alt }: { src?: string | Blob; alt?: string }) {
  const { scope: ownerType } = useSessionApi();
  const scope = useContext(imageScope), generated = typeof src === 'string' ? generatedReference(src) : null, image = typeof src === 'string' ? replyImageReference(src) : null;
  if (scope && generated) return <GeneratedPreview {...scope} imageId={generated} alt={alt} />;
  return scope && ownerType === 'project' && image ? <ReplyImage {...scope} {...image} alt={alt ?? ''} />
    : <span className="agent-image-alt">{alt || 'Image unavailable.'}</span>;
}
function containsImage(children: ReactNode): boolean {
  return Children.toArray(children).some((child) => isValidElement<{ children?: ReactNode }>(child)
    && (child.type === MarkdownImage || containsImage(child.props.children)));
}
const messageUrl: UrlTransform = (value, key, node) => key === 'src' && node.tagName === 'img'
  ? (replyImageReference(value) || generatedReference(value) ? value : '') : defaultUrlTransform(value);
const components: Components = {
  span({children,...props}) {return (props as Record<string,unknown>)['data-studio-stream']==='1'?<StreamLeaf text={Children.toArray(children).filter(v=>typeof v==='string').join('')}/>:<span>{children}</span>;},
  pre({ children }) {
    const code = isValidElement<{ children?: ReactNode; className?: string }>(children) ? children.props : {};
    return <CodeBlock text={typeof code.children === 'string' ? code.children : ''} language={code.className?.replace(/^language-/, '').slice(0, 32)} />;
  },
  // Only opaque registered evidence may fetch a fixed authenticated endpoint.
  img: MarkdownImage,
  a({ href, children }) { return containsImage(children) ? <>{children}</> : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>; },
};

function AgentMarkdown({text,projectId,sessionId,live=false}:{text:string;projectId?:string;sessionId?:string;live?:boolean}) {
  const visible=transcriptText(text),root=useRef<HTMLDivElement>(null);
  const [engine]=useState(()=>new TextStream()),[locked,setLocked]=useState<string|null>(null),[instant,setInstant]=useState(0),[armed,setArmed]=useState(live);
  const baseline=useRef({raw:'',semantic:''});
  const seeded=useRef(false);
  if(live&&!armed&&locked===null)setArmed(true);
  const previousInstant=useRef(0),rendered=locked??visible;
  const enabled=armed&&rendered.length<=8192,context=useMemo(()=>({engine,enabled}),[engine,enabled]);
  const scope = useMemo(() => projectId && sessionId ? { projectId, sessionId } : null, [projectId, sessionId]);
  const content=useMemo(()=><Markdown skipHtml components={components} urlTransform={messageUrl} rehypePlugins={enabled?[streamTextPlugin]:undefined}>{rendered}</Markdown>,[rendered,enabled]);
  useLayoutEffect(()=>{
    if(!armed&&root.current){
      const parts:string[]=[],walker=document.createTreeWalker(root.current,NodeFilter.SHOW_TEXT);
      if(rendered.length<=8192)while(walker.nextNode()){const node=walker.currentNode;if(!node.parentElement?.closest('button,.agent-code-bar,.agent-reply-image,.agent-image-loading,.agent-image-unavailable'))parts.push(node.textContent??'');}
      baseline.current={raw:rendered,semantic:parts.join('')};
      return;
    }
    if(!seeded.current){engine.seed(baseline.current.raw,baseline.current.semantic);seeded.current=true;}
    if(root.current)engine.configure(root.current,rendered,live&&locked===null&&enabled&&!rendered.includes('studio-image:')&&!rendered.includes('studio-generated-image:')&&previousInstant.current===instant);
    previousInstant.current=instant;
  },[armed,engine,rendered,live,locked,enabled,instant]);
  useLayoutEffect(()=>()=>engine.dispose(),[engine]);
  useEffect(()=>{
    const media=matchMedia('(prefers-reduced-motion: reduce)');
    const selection=()=>{
      const value=document.getSelection(),element=root.current;
      if(value&&!value.isCollapsed&&element&&value.rangeCount&&value.getRangeAt(0).intersectsNode(element)){
        engine.finish();setLocked(old=>old??visible);
      }else if(locked!==null){setLocked(null);setInstant(value=>value+1);}
    };
    const flush=()=>{engine.finish();setLocked(null);setInstant(value=>value+1);};
    document.addEventListener('selectionchange',selection);document.addEventListener('visibilitychange',flush);media.addEventListener('change',flush);
    return()=>{document.removeEventListener('selectionchange',selection);document.removeEventListener('visibilitychange',flush);media.removeEventListener('change',flush);};
  },[live,locked,visible,engine]);
  const gesture=()=>{engine.finish();if(locked!==null)flushSync(()=>{setLocked(null);setInstant(value=>value+1);});};
  return <imageScope.Provider value={scope}><StreamContext.Provider value={context}><div ref={root} className="agent-message-text agent-markdown" aria-live="off"
    onPointerDownCapture={event=>{if(!event.shiftKey||(event.target as Element).closest('.agent-copy'))gesture();}}
    onKeyDownCapture={event=>{if(['Enter',' '].includes(event.key)&&(event.target as Element).closest('button'))gesture();}}
    onClickCapture={event=>{if((event.target as Element).closest('.agent-copy'))gesture();}}>{content}</div></StreamContext.Provider></imageScope.Provider>;
}
export const MessageText=memo(function MessageText({text,markdown=false,projectId,sessionId,live=false}:{text:string;markdown?:boolean;projectId?:string;sessionId?:string;live?:boolean}) {
  return markdown?<AgentMarkdown text={text} projectId={projectId} sessionId={sessionId} live={live}/>:<div className="agent-message-text">{transcriptText(text)}</div>;
});
