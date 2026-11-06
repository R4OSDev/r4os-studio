import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { SessionItem } from '../../../../shared/agent-sessions';
import { toolLabels, useSessionApi } from './api';
import { DevelopmentCard, DevelopmentImage, developmentRef } from './DevelopmentCard';
import { CodeBlock, MessageText } from './Transcript';
import { SkillCard } from './SkillCard';
import { WebSearchCard } from './WebSearchCard';
import { roadmapLabels, RoadmapReceipt } from './RoadmapReceipt';
import { RemoteReceipt } from './RemoteReceipt';
import { AttachmentHistory } from './AttachmentHistory';
import { GeneratedCard } from './GeneratedImage';
import './streaming.css';

type ToolEntry = { item: SessionItem; jobId?: string };
type TranscriptEntry = { kind: 'tools'; key: string; runId: string; tools: ToolEntry[] }
  | { kind: 'message'; key: string; item: SessionItem };
const itemKey = (item: SessionItem) => item.runId + ':' + item.id;
const toolLabel = (item: SessionItem) => item.type === 'terminal' ? 'Terminal' : item.tool === 'web_search' ? 'Web search' : roadmapLabels[item.tool ?? ''] ?? toolLabels[item.tool ?? ''] ?? 'Tool call';

function GitHubReceipt({ value }: { value: unknown }) {
  const ref = value as { id?: string; state?: string; commit?: string; pushed?: boolean } | null;
  if (!ref || typeof ref.id !== 'string' || !/^[a-f0-9-]{36}$/.test(ref.id)) return null;
  return <dl className="development-target" aria-label="GitHub push receipt"><div><dt>GitHub job</dt><dd>{ref.id}</dd></div>
    <div><dt>Status</dt><dd>{typeof ref.state === 'string' ? ref.state.slice(0, 40) : 'Unknown'}{ref.pushed ? ' · Push confirmed' : ''}</dd></div>
    {typeof ref.commit === 'string' && /^[a-f0-9]{40,64}$/.test(ref.commit) && <div><dt>Commit</dt><dd>{ref.commit.slice(0, 12)}</dd></div>}</dl>;
}

function TerminalLifetime({ value }: { value: SessionItem }) {
  if (value.type !== 'terminal' && !(['studio.exec_command', 'studio.write_stdin', 'studio.terminate_process'].includes(value.tool ?? '') && value.timing?.version === 1)) return null;
  const seconds = (number: number | null | undefined) => typeof number === 'number' && Number.isFinite(number) && number >= 0 ? `${(number / 1000).toFixed(1)} s` : 'Unavailable';
  const stamp = (text: string | null | undefined) => text && Number.isFinite(Date.parse(text)) ? new Date(text).toLocaleString() : 'Unavailable';
  if (!value.timing) return <p className="agent-terminal-hint">Lifetime measurement unavailable for this saved process.</p>;
  return <div aria-label="Original terminal lifetime">
    <p>Elapsed ({value.timing.final ? 'final observation' : 'observed'}): {seconds(value.elapsedMilliseconds)} · Remaining lifetime: {seconds(value.remainingLifetimeMilliseconds)}</p>
    <p className="agent-terminal-hint">Started: {stamp(value.startedAt)} · Original deadline: {stamp(value.deadlineAt)}</p>
  </div>;
}

const ToolDetails = memo(function ToolDetails({ i, jobId, projectId, sessionId, token }: { i: SessionItem; jobId?: string; projectId: string; sessionId: string; token: string }) {
  const { scope } = useSessionApi();
  return <>
        {i.tool === 'web_search' || i.tool === 'studio.web_search' ? <WebSearchCard value={i.webSearch} /> : <CodeBlock text={JSON.stringify(i.arguments, null, 2) ?? ''} label="Copy arguments" language="Arguments" />}
        {(i.tool === 'image_gen.imagegen' || i.tool === 'studio.generate_image' || i.generatedAsset) && <GeneratedCard value={i.generatedImage} asset={i.generatedAsset} projectId={projectId} sessionId={sessionId} status={i.status} />}
        {i.generatedImages?.filter(image => image.id !== i.generatedImage?.id).map(image => <GeneratedCard key={image.id} value={image} asset={null} projectId={projectId} sessionId={sessionId} status={i.status} />)}
        {i.imageErrors?.map((error,index) => <p key={index} role="status">{error}</p>)}
        {!!i.generatedImages?.length && i.imageDelivery === 'reference-only' && <p>This model received the image reference. It did not receive the image pixels.</p>}
        {i.output && <CodeBlock text={i.output} label="Copy output" language="Output" />}{i.truncated === true && <p>Output truncated.</p>}
        {['studio.validate_skill', 'studio.save_skill'].includes(i.tool ?? '') && <SkillCard value={i.skill} />}
        {i.tool === 'studio.push_project' && <GitHubReceipt value={i.github} />}
        {scope === 'project' && roadmapLabels[i.tool ?? ''] && <RoadmapReceipt value={i.roadmap} />}
        {scope === 'project' && i.remote && <RemoteReceipt value={i.remote} />}
        {i.tool === 'studio.stop_development_job' && i.developmentStop?.version === 1 && <p>
          {i.developmentStop.confirmed ? (i.developmentStop.outcome === 'already-ended' ? 'Already ended. ' : i.developmentStop.outcome === 'not-started' ? 'Application was not started. ' : 'Stop confirmed. ') : 'Stop unconfirmed. '}
          {i.developmentStop.scope === 'worker' ? 'Host worker only. ' : 'Owned application process. '}
          Job status: {i.developmentStop.jobState}. {i.developmentStop.guestEffectsMayRemain === true && 'Completed guest writes are retained.'}
        </p>}
        {typeof i.nextLine === 'number' && <p>More lines available from line {i.nextLine}.</p>}
        {typeof i.lineTruncated === 'number' && <p>Line {i.lineTruncated} exceeds the output limit.</p>}
        {typeof i.nextOffset === 'number' && <p>More entries available from offset {i.nextOffset}.</p>}
        {typeof i.skippedFiles === 'number' && i.skippedFiles > 0 && <p>{i.skippedFiles} files were not searched.</p>}
        {i.partialChangesPossible === true && <p>Partial changes may remain.</p>}
        {i.files != null && typeof i.files === 'object' && <CodeBlock text={JSON.stringify(i.files, null, 2)} label="Copy changed files" language="Files" />}
        <TerminalLifetime value={i} />
        {i.exitCode != null && <p>Exit code {i.exitCode}</p>}{i.error && <p>{i.error}</p>}
        {i.captureState === 'confirmed' && <p>Screenshot saved.{i.imageDelivery === 'reference-only' && ' This model received the image reference without pixels.'}</p>}
        {i.visionAnalysis && <div aria-label="Screenshot analysis">
          <p>{({ 'not-requested': 'Analysis not requested.', native: 'Image delivered directly to the main model.', completed: 'External Vision analysis completed.', failed: 'Analysis unavailable. The saved screenshot is retained.', unknown: 'Analysis unconfirmed. The saved screenshot is retained.' })[i.visionAnalysis.state]}</p>
          {i.visionAnalysis.model && <p>Vision model: {i.visionAnalysis.model}</p>}
          {i.visionAnalysis.text && <p>{i.visionAnalysis.text}</p>}
          {i.visionAnalysis.reason && <p>{i.visionAnalysis.reason}</p>}
        </div>}
        {scope === 'project' && <DevelopmentImage projectId={projectId} value={i.image} />}
        {scope === 'project' && jobId && <DevelopmentCard projectId={projectId} token={token} jobId={jobId} />}
  </>;
});

const ToolCallBlock = memo(function ToolCallBlock({ tools, projectId, sessionId, token }: { tools: ToolEntry[]; projectId: string; sessionId: string; token: string }) {
  const [expanded, setExpanded] = useState(false), [opened, setOpened] = useState<Set<string>>(() => new Set());
  const [page, setPage] = useState<string | null>(null);
  const first = expanded ? (page ? Math.max(0, tools.findIndex(tool => itemKey(tool.item) === page)) : Math.max(0, tools.length - 60)) : Math.max(0, tools.length - 3);
  const visible = tools.slice(first, first + (expanded ? 60 : 3));
  const listId = useId(), list = useRef<HTMLDivElement>(null), follow = useRef(true);
  useLayoutEffect(() => {
    if (follow.current && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [tools.length]);

  function toggleBlock() {
    if (expanded) { setOpened(new Set()); setPage(null); follow.current=true; }
    setExpanded(!expanded);
  }

  return <section className={`agent-tool-block${expanded ? ' expanded' : ''}`} aria-label="Tool-call block">
    <button className="agent-tool-block-toggle" type="button" aria-expanded={expanded} aria-controls={listId}
      aria-label={expanded ? 'Collapse tool-call block' : 'Expand tool-call block'} onClick={toggleBlock}>
      <span className="agent-tool-block-chevron" aria-hidden="true">›</span>
      <span>Tool calls</span><span className="agent-tool-count">{tools.length}</span>
    </button>
    <div className="agent-tool-list" id={listId} ref={list} tabIndex={0} role="group" aria-label="Tool calls"
      onScroll={(event) => { const element = event.currentTarget; follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24; if(expanded&&!follow.current)setPage(old=>old??itemKey(tools[first].item)); }}>
      {expanded && first > 0 && <button type="button" className="agent-older" onClick={() => { follow.current=false;setPage(itemKey(tools[Math.max(0, first-30)].item)); }}>Earlier tool calls</button>}
      {visible.map(({ item: i, jobId }) => <details key={itemKey(i)} open={opened.has(itemKey(i))} className={`agent-tool ${i.status ?? ''}`}
        onToggle={(event) => { const active = event.currentTarget.open; setOpened(previous => { if(previous.has(itemKey(i))===active)return previous; const next = new Set(previous); if (active) next.add(itemKey(i)); else next.delete(itemKey(i)); return next; }); if (active) { follow.current = false; setPage(old=>old??itemKey(tools[Math.max(0,tools.length-60)].item)); setExpanded(true); } }}>
        <summary><span title={toolLabel(i)}>{toolLabel(i)}</span><span className="agent-tool-status">{i.status}</span></summary>
        {opened.has(itemKey(i)) && <ToolDetails i={i} jobId={jobId} projectId={projectId} sessionId={sessionId} token={token} />}
      </details>)}
      {expanded && first + 60 < tools.length && <button type="button" className="agent-older" onClick={() => { follow.current=false;setPage(itemKey(tools[first+30].item)); }}>Later tool calls</button>}
    </div>
  </section>;
});


// Reuse unchanged group arrays so a live answer does not rerender closed tools.
class Groups {
  private previous = new Map<string, TranscriptEntry>();
  project(items: SessionItem[]) {
    const entries: TranscriptEntry[] = [], jobs = new Set<string>();
    for (const item of items) {
      const key = itemKey(item);
      if (item.type === 'tool' || item.type === 'terminal') {
        const reference = developmentRef(item.development), jobId = reference && !jobs.has(reference.jobId) ? reference.jobId : undefined;
        if (jobId) jobs.add(jobId);
        const previous = entries.at(-1), tool = {item, jobId};
        if (previous?.kind === 'tools' && previous.runId === item.runId) previous.tools.push(tool);
        else entries.push({kind:'tools', key, runId:item.runId, tools:[tool]});
      } else entries.push({kind:'message', key, item});
    }
    for (let index=0; index<entries.length; index++) {
      const value=entries[index], old=this.previous.get(value.key);
      if (old?.kind === 'tools' && value.kind === 'tools' && old.tools.length === value.tools.length
          && old.tools.every((tool, offset) => tool.item === value.tools[offset].item && tool.jobId === value.tools[offset].jobId)) entries[index]=old;
      else if (old?.kind === 'message' && value.kind === 'message' && old.item === value.item) entries[index]=old;
    }
    this.previous = new Map(entries.map(entry => [entry.key, entry]));
    return entries;
  }
}

const Message = memo(function Message({item, projectId, sessionId, live}: {item: SessionItem; projectId: string; sessionId: string; live: boolean}) {
  return <article data-message-id={item.id} data-run-id={item.runId} className={`agent-message ${item.type}`}>
    {item.type !== 'notice' && <div className="agent-message-role">{item.type === 'user' ? 'You' : 'Agent'}</div>}
    <MessageText text={item.text || (item.type === 'user' && Array.isArray(item.attachments) ? `${item.attachments.length} attachment${item.attachments.length === 1 ? '' : 's'}` : '')} markdown={item.type === 'assistant'} projectId={projectId} sessionId={sessionId} live={live}/>
    {item.type === 'user' && Array.isArray(item.attachments) && <AttachmentHistory files={item.attachments} projectId={projectId} sessionId={sessionId} />}
  </article>;
});

const WINDOW = 80, STEP = 40;
export const SessionTranscript=memo(function SessionTranscript({items, projectId, sessionId, token, liveText, before, older, loadOlder, log, following, pauseFollowing, resumeFollowing, viewChanged}: {
  items:SessionItem[];projectId:string;sessionId:string;token:string;liveText?:{runId:string;itemId:string}|null;
  before:number|null;older:boolean;loadOlder:()=>Promise<void>;log:RefObject<HTMLDivElement|null>;following:boolean;pauseFollowing:()=>void;resumeFollowing:()=>void;viewChanged:(latest:boolean)=>void;
}) {
  const [groups]=useState(()=>new Groups()), entries=useMemo(()=>groups.project(items),[groups,items]);
  const [startKey,setStartKey]=useState<string|null>(null), root=useRef<HTMLDivElement>(null);
  const anchor=useRef<{key:string;top:number}|null>(null), pendingEarlier=useRef<string|null>(null);
  if(following&&startKey!==null)setStartKey(null);
  const start = !following && startKey ? Math.max(0,entries.findIndex(entry=>entry.key===startKey)) : Math.max(0,entries.length-WINDOW), end=Math.min(entries.length,start+WINDOW);
  useLayoutEffect(()=>{viewChanged(end===entries.length);},[end,entries.length,viewChanged]);
  const capture=()=>{
    const viewport=log.current; if(!viewport)return;
    const top=viewport.getBoundingClientRect().top;
    const row=Array.from(root.current?.querySelectorAll<HTMLElement>('[data-transcript-key]')??[]).find(element=>element.getBoundingClientRect().bottom>top);
    if(row)anchor.current={key:row.dataset.transcriptKey!,top:row.getBoundingClientRect().top};
  };
  useLayoutEffect(()=>{
    if(following){
      anchor.current=null;pendingEarlier.current=null;
      return;
    }
    if (pendingEarlier.current && entries[0]?.key !== pendingEarlier.current) {
      const offset=entries.findIndex(entry=>entry.key===pendingEarlier.current); pendingEarlier.current=null;
      setStartKey(entries[Math.max(0,offset-STEP)]?.key??null);return;
    }
    if(!following && startKey===null && entries.length>WINDOW)setStartKey(entries[start].key);
    const saved=anchor.current;
    if(saved&&log.current){
      const row=Array.from(root.current?.querySelectorAll<HTMLElement>('[data-transcript-key]')??[]).find(element=>element.dataset.transcriptKey===saved.key);
      if(row){log.current.scrollBy({top:row.getBoundingClientRect().top-saved.top});pauseFollowing();}
      anchor.current=null;
    }
  },[entries,following,startKey,start,log,pauseFollowing]);
  useEffect(()=>{
    const selection=()=>{const value=document.getSelection();if(value&&!value.isCollapsed&&value.rangeCount&&root.current&&value.getRangeAt(0).intersectsNode(root.current))pauseFollowing();};
    document.addEventListener('selectionchange',selection);return()=>document.removeEventListener('selectionchange',selection);
  },[pauseFollowing]);
  const earlier=()=>{
    capture();pauseFollowing();
    if(start>0)setStartKey(entries[Math.max(0,start-STEP)].key);
    else if(before){pendingEarlier.current=entries[0]?.key??null;setStartKey(entries[0]?.key??null);void loadOlder();}
  };
  return <div ref={root}>
    {(start>0||before!==null)&&<button type="button" className="agent-older" disabled={older} onClick={earlier}>{older?'Loading…':'Load earlier messages'}</button>}
    {entries.length>WINDOW&&<p className="agent-history-window" role="status">Showing {start+1}–{end} of {entries.length} loaded blocks</p>}
    {entries.slice(start,end).map(entry=><div key={entry.key} data-transcript-key={entry.key}>{entry.kind==='tools'
      ?<ToolCallBlock tools={entry.tools} projectId={projectId} sessionId={sessionId} token={token}/>
      :<Message item={entry.item} projectId={projectId} sessionId={sessionId} live={entry.item.status==='running'&&liveText?.runId===entry.item.runId&&liveText?.itemId===entry.item.id}/>}</div>)}
    {end<entries.length&&<button type="button" className="agent-older" onClick={()=>{capture();pauseFollowing();setStartKey(entries[start+STEP].key);}}>Load later messages</button>}
    {startKey!==null&&!following&&<button type="button" className="agent-older" onClick={()=>{anchor.current=null;setStartKey(null);resumeFollowing();}}>Latest messages</button>}
  </div>;
});
