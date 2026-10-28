import { useId, useLayoutEffect, useRef, useState } from 'react';
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

function ToolCallBlock({ tools, projectId, sessionId, token }: { tools: ToolEntry[]; projectId: string; sessionId: string; token: string }) {
  const { scope } = useSessionApi();
  const [expanded, setExpanded] = useState(false), [opened, setOpened] = useState<Set<string>>(() => new Set());
  const listId = useId(), list = useRef<HTMLDivElement>(null), follow = useRef(true);
  useLayoutEffect(() => {
    if (follow.current && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [tools.length]);

  function toggleBlock() {
    if (expanded) {
      list.current?.querySelectorAll<HTMLDetailsElement>('.agent-tool[open]').forEach((tool) => { tool.open = false; });
    }
    setExpanded(!expanded);
  }

  return <section className={`agent-tool-block${expanded ? ' expanded' : ''}`} aria-label="Tool-call block">
    <button className="agent-tool-block-toggle" type="button" aria-expanded={expanded} aria-controls={listId}
      aria-label={expanded ? 'Collapse tool-call block' : 'Expand tool-call block'} onClick={toggleBlock}>
      <span className="agent-tool-block-chevron" aria-hidden="true">›</span>
      <span>Tool calls</span><span className="agent-tool-count">{tools.length}</span>
    </button>
    <div className="agent-tool-list" id={listId} ref={list} tabIndex={0} role="group" aria-label="Tool calls"
      onScroll={(event) => { const element = event.currentTarget; follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24; }}>
      {tools.map(({ item: i, jobId }) => <details key={itemKey(i)} className={`agent-tool ${i.status ?? ''}`}
        onToggle={(event) => { const active = event.currentTarget.open; setOpened(previous => { const next = new Set(previous); if (active) next.add(itemKey(i)); else next.delete(itemKey(i)); return next; }); if (active) { follow.current = false; setExpanded(true); } }}>
        <summary><span title={toolLabel(i)}>{toolLabel(i)}</span><span className="agent-tool-status">{i.status}</span></summary>
        {i.tool === 'web_search' ? <WebSearchCard value={i.webSearch} /> : <CodeBlock text={JSON.stringify(i.arguments, null, 2) ?? ''} label="Copy arguments" language="Arguments" />}
        {opened.has(itemKey(i)) && (i.tool === 'image_gen.imagegen' || i.generatedAsset) && <GeneratedCard value={i.generatedImage} asset={i.generatedAsset} projectId={projectId} sessionId={sessionId} status={i.status} />}
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
        {i.exitCode != null && <p>Exit code {i.exitCode}</p>}{i.error && <p>{i.error}</p>}
        {scope === 'project' && <DevelopmentImage projectId={projectId} value={i.image} />}
        {scope === 'project' && jobId && <DevelopmentCard projectId={projectId} token={token} jobId={jobId} />}
      </details>)}
    </div>
  </section>;
}

export function SessionTranscript({ items, projectId, sessionId, token }: { items: SessionItem[]; projectId: string; sessionId: string; token: string }) {
  const entries: TranscriptEntry[] = [], jobs = new Set<string>();
  for (const item of items) {
    const key = itemKey(item);
    if (item.type === 'tool' || item.type === 'terminal') {
      const reference = developmentRef(item.development);
      const jobId = reference && !jobs.has(reference.jobId) ? reference.jobId : undefined;
      if (jobId) jobs.add(jobId);
      const previous = entries.at(-1), tool = { item, jobId };
      if (previous?.kind === 'tools' && previous.runId === item.runId) previous.tools.push(tool);
      else entries.push({ kind: 'tools', key, runId: item.runId, tools: [tool] });
    } else entries.push({ kind: 'message', key, item });
  }
  return entries.map((entry) => entry.kind === 'tools'
    ? <ToolCallBlock key={entry.key} tools={entry.tools} projectId={projectId} sessionId={sessionId} token={token} />
    : <article key={entry.key} className={`agent-message ${entry.item.type}`}>
      {entry.item.type !== 'notice' && <div className="agent-message-role">{entry.item.type === 'user' ? 'You' : 'Agent'}</div>}
      <MessageText text={entry.item.text || (entry.item.type === 'user' && Array.isArray(entry.item.attachments) ? `${entry.item.attachments.length} attachment${entry.item.attachments.length === 1 ? '' : 's'}` : '')} markdown={entry.item.type === 'assistant'} projectId={projectId} sessionId={sessionId} />
      {entry.item.type === 'user' && Array.isArray(entry.item.attachments) && <AttachmentHistory files={entry.item.attachments} projectId={projectId} sessionId={sessionId} />}
    </article>);
}
