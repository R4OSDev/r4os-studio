import { useId, useLayoutEffect, useRef, useState } from 'react';
import type { SessionItem } from '../../../../shared/agent-sessions';
import { toolLabels } from './api';
import { DevelopmentCard, DevelopmentImage, developmentRef } from './DevelopmentCard';
import { CodeBlock, MessageText } from './Transcript';

type ToolEntry = { item: SessionItem; jobId?: string };
type TranscriptEntry = { kind: 'tools'; key: string; runId: string; tools: ToolEntry[] }
  | { kind: 'message'; key: string; item: SessionItem };
const itemKey = (item: SessionItem) => item.runId + ':' + item.id;

function ToolCallBlock({ tools, projectId, token }: { tools: ToolEntry[]; projectId: string; token: string }) {
  const [expanded, setExpanded] = useState(false);
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
        onToggle={(event) => { if (event.currentTarget.open) { follow.current = false; setExpanded(true); } }}>
        <summary><span title={i.type === 'terminal' ? 'Terminal' : toolLabels[i.tool ?? ''] ?? 'Tool call'}>{i.type === 'terminal' ? 'Terminal' : toolLabels[i.tool ?? ''] ?? 'Tool call'}</span><span className="agent-tool-status">{i.status}</span></summary>
        <CodeBlock text={JSON.stringify(i.arguments, null, 2) ?? ''} label="Copy arguments" language="Arguments" />
        {i.output && <CodeBlock text={i.output} label="Copy output" language="Output" />}{i.truncated === true && <p>Output truncated.</p>}
        {typeof i.nextLine === 'number' && <p>More lines available from line {i.nextLine}.</p>}
        {typeof i.lineTruncated === 'number' && <p>Line {i.lineTruncated} exceeds the output limit.</p>}
        {typeof i.nextOffset === 'number' && <p>More entries available from offset {i.nextOffset}.</p>}
        {typeof i.skippedFiles === 'number' && i.skippedFiles > 0 && <p>{i.skippedFiles} files were not searched.</p>}
        {i.partialChangesPossible === true && <p>Partial changes may remain.</p>}
        {i.files != null && typeof i.files === 'object' && <CodeBlock text={JSON.stringify(i.files, null, 2)} label="Copy changed files" language="Files" />}
        {i.exitCode != null && <p>Exit code {i.exitCode}</p>}{i.error && <p>{i.error}</p>}
        <DevelopmentImage projectId={projectId} value={i.image} />
        {jobId && <DevelopmentCard projectId={projectId} token={token} jobId={jobId} />}
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
    ? <ToolCallBlock key={entry.key} tools={entry.tools} projectId={projectId} token={token} />
    : <article key={entry.key} className={`agent-message ${entry.item.type}`}>
      {entry.item.type !== 'notice' && <div className="agent-message-role">{entry.item.type === 'user' ? 'You' : 'Agent'}</div>}
      <MessageText text={entry.item.text ?? ''} markdown={entry.item.type === 'assistant'} projectId={projectId} sessionId={sessionId} />
    </article>);
}
