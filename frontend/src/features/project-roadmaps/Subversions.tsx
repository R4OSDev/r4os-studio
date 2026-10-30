import { useState } from 'react';
import { Icon } from '../../app/Icon';
import type { RoadmapBinding, RoadmapItem, RoadmapMutation, RoadmapSubversionHeader, RoadmapTarget } from '../../../../shared/project-roadmaps';
import { ProjectRequestError, projectRequestId } from '../projects/api';
import { mutate } from './api';
import { itemStatusLabels, versionStatusLabels } from './model';
import { useRoadmapPage } from './useRoadmapPage';

export interface EntryEditor {
  title: string; target: RoadmapTarget; initial: NonNullable<RoadmapMutation['input']>; create?: boolean;
  notesMode?: 'edit' | 'append_notes' | 'replace_notes';
}
interface Shared {
  id: string; token: string; versionId: string; binding: RoadmapBinding;
  disabled: boolean; edit: (editor: EntryEditor) => void; changed: () => void; busyChanged: (busy: boolean) => void;
}
const entityName = (kind: string) => kind === 'acceptance' ? 'acceptance item' : kind;
const scopeKey = (id: string, target: RoadmapTarget) => `studio.roadmap.action.${id}.${target.kind}.${'versionId' in target ? target.versionId : ''}.${'subversionId' in target ? target.subversionId : ''}.${target.id ?? 'order'}`;
function hasPending(id: string, target: RoadmapTarget) {
  try { return !!sessionStorage.getItem(scopeKey(id, target)); } catch { return false; }
}

function useActions(props: Shared) {
  const [error, setError] = useState('');
  async function perform(action: RoadmapMutation['action'], target: RoadmapTarget, input: RoadmapMutation['input']) {
    if (props.disabled) return;
    const key = scopeKey(props.id, target);
    props.busyChanged(true); setError('');
    try {
      const original = sessionStorage.getItem(key);
      const body: RoadmapMutation = original ? JSON.parse(original) : { requestId: projectRequestId(),
        expectedRevision: props.binding.revision, currentVersionId: props.binding.currentVersionId, action, target, input };
      if (JSON.stringify(body.target) !== JSON.stringify(target)) throw new Error('The original target needs reconciliation. Browser request data was preserved.');
      sessionStorage.setItem(key, JSON.stringify(body));
      await mutate(props.id, props.token, body);
      sessionStorage.removeItem(key); props.changed();
    } catch (cause) {
      const failure = cause as ProjectRequestError;
      if (failure.status >= 400 && failure.status < 500) sessionStorage.removeItem(key);
      setError(failure.message || 'The result could not be confirmed. Confirm the original change before editing this entry.');
    } finally { props.busyChanged(false); }
  }
  function remove(target: RoadmapTarget, label: string, consequences = 'Its notes will also be removed.') {
    if (hasPending(props.id, target) || window.confirm(`Delete ${label}? ${consequences}`)) void perform('delete', target, { confirm: true });
  }
  return { error, perform, remove };
}

function NoteDetails({ notes }: { notes: string }) {
  return <details className="roadmap-notes"><summary>Notes{notes ? '' : ' (empty)'}</summary>
    <div className="roadmap-note-text" tabIndex={0}>{notes || 'No notes yet.'}</div></details>;
}

function ItemCollection(props: Shared & { subversionId: string; kind: 'task' | 'acceptance' }) {
  const collection = props.kind === 'task' ? 'tasks' : 'acceptances';
  const path = `/versions/${props.versionId}/subversions/${props.subversionId}/${collection}`;
  const list = useRoadmapPage<RoadmapItem>(props.id, path, props.binding.revision);
  const actions = useActions(props);
  const target: RoadmapTarget = { kind: props.kind, versionId: props.versionId, subversionId: props.subversionId };
  const items = list.page?.items ?? [];
  const noun = entityName(props.kind);
  const collectionLabel = props.kind === 'task' ? 'tasks' : 'acceptance items';
  return <section className="roadmap-item-collection" aria-label={props.kind === 'task' ? 'Tasks' : 'Acceptance items'}>
    <div className="roadmap-collection-heading"><h4>{props.kind === 'task' ? 'Tasks' : 'Acceptance items'}</h4>
      <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: `New ${noun}`, target,
        initial: { description: '', notes: '', status: 'open' }, create: true })}>Add {noun}</button></div>
    {(list.error || actions.error) && <p className="project-error" role="alert">{list.error || actions.error}</p>}
    {list.loading && <p role="status">Loading {collectionLabel}…</p>}
    {(['open', 'done', 'discarded'] as const).map((status) => <div className="roadmap-item-group" key={status}>
      <h5><span className="roadmap-status" data-status={status}>{itemStatusLabels[status]}</span><span className="roadmap-group-count">{items.filter((item) => item.status === status).length}{list.page?.nextCursor ? ' loaded' : ''}</span></h5>
      <ul>{items.filter((item) => item.status === status).map((item) => {
        const reference = { ...target, id: item.id };
        const pending = hasPending(props.id, reference);
        return <li key={item.id} className="roadmap-item" aria-label={`${noun}: ${item.description}`}>
          <p className="roadmap-item-description" tabIndex={0}>{item.description}</p>
          <span className="roadmap-status" data-status={item.status}>{itemStatusLabels[item.status]}</span>
          <NoteDetails notes={item.notes} />
          <div className="roadmap-entry-actions" role="group" aria-label="Entry actions">
            {pending ? <button type="button" disabled={props.disabled} onClick={() => void actions.perform('update', reference, {})}>Confirm original change</button> : <>
              <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: `Edit ${noun}`, target: reference,
                initial: { description: item.description, notes: item.notes, status: item.status } })}>Edit {noun}</button>
              <button type="button" disabled={props.disabled} onClick={() => void actions.perform('update', reference, { status: item.status === 'open' ? 'done' : 'open' })}>{item.status === 'open' ? 'Mark done' : 'Reopen'}</button>
              <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: `Append ${noun} notes`, target: reference, initial: { notes: '' }, notesMode: 'append_notes' })}>Append notes</button>
              <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: `Edit ${noun} notes`, target: reference, initial: { notes: item.notes }, notesMode: 'replace_notes' })}>Edit notes</button>
              <button type="button" className="roadmap-delete" disabled={props.disabled} onClick={() => actions.remove(reference, `${noun} “${item.description.slice(0, 160)}”`)}>Delete {noun}</button>
            </>}
          </div>
        </li>;
      })}</ul>
      {!list.loading && !items.some((item) => item.status === status) && <p className="project-message">No {status} {collectionLabel}{list.page?.nextCursor ? ' loaded yet' : ''}.</p>}
    </div>)}
    {list.page?.nextCursor && <button type="button" disabled={props.disabled || list.busy} onClick={() => void list.more()}>{list.busy ? 'Loading…' : `More ${collectionLabel}`}</button>}
  </section>;
}

function Subversion({ sub, ...props }: Shared & { sub: RoadmapSubversionHeader }) {
  const expandedKey = `studio.roadmap.expanded.${props.id}.${sub.id}`;
  const [expanded, setExpanded] = useState(() => { try { return sessionStorage.getItem(expandedKey) === '1'; } catch { return false; } });
  const actions = useActions(props);
  const target: RoadmapTarget = { kind: 'subversion', versionId: props.versionId, id: sub.id };
  const pending = hasPending(props.id, target);
  return <details className="roadmap-subversion" open={expanded} onToggle={(event) => {
    const open = event.currentTarget.open; setExpanded(open);
    try { if (open) sessionStorage.setItem(expandedKey, '1'); else sessionStorage.removeItem(expandedKey); } catch { /* Expanding does not require browser storage. */ }
  }}>
    <summary>
      <span className="roadmap-subversion-title"><Icon name="chevron"/><span><strong>{sub.number}</strong><span>{sub.title}</span></span></span>
      <span className="roadmap-status" data-status={sub.status}>{versionStatusLabels[sub.status]}</span>
      <span className="roadmap-subversion-progress">{(['tasks','acceptances'] as const).map(kind=><span key={kind}>
        <span>{kind==='tasks'?'Tasks':'Acceptance items'}</span><strong>{sub.progress[kind].done} / {sub.progress[kind].total}</strong>
        <span>done{sub.progress[kind].discarded ? ` · ${sub.progress[kind].discarded} discarded` : ''}</span>
      </span>)}</span>
    </summary>
    {expanded && <div className="roadmap-subversion-body">
      <section className="roadmap-subversion-description" aria-label="Description and notes"><h4>Description</h4>
        <p className="roadmap-item-description" tabIndex={0}>{sub.description || 'No description yet.'}</p>
        <NoteDetails notes={sub.notes} />
      </section>
      {actions.error && <p className="project-error" role="alert">{actions.error}</p>}
      <div className="roadmap-entry-actions" role="group" aria-label="Entry actions">
        {pending ? <button type="button" disabled={props.disabled} onClick={() => void actions.perform('update', target, {})}>Confirm original change</button> : <>
          <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: 'Edit subversion', target,
            initial: { number: sub.number, title: sub.title, description: sub.description, notes: sub.notes, status: sub.status } })}>Edit subversion</button>
          <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: 'Append subversion notes', target, initial: { notes: '' }, notesMode: 'append_notes' })}>Append notes</button>
          <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: 'Edit subversion notes', target, initial: { notes: sub.notes }, notesMode: 'replace_notes' })}>Edit notes</button>
          <button type="button" className="roadmap-delete" disabled={props.disabled} onClick={() => actions.remove(target, `subversion ${sub.number} “${sub.title}”`,
            `Its ${sub.progress.tasks.total} tasks, ${sub.progress.acceptances.total} acceptance items and their notes will also be removed.`)}>Delete subversion</button>
        </>}
      </div>
      <ItemCollection {...props} subversionId={sub.id} kind="task" />
      <ItemCollection {...props} subversionId={sub.id} kind="acceptance" />
    </div>}
  </details>;
}

export function Subversions(props: Shared) {
  const list = useRoadmapPage<RoadmapSubversionHeader>(props.id, `/versions/${props.versionId}/subversions`, props.binding.revision);
  const actions = useActions(props);
  const target: RoadmapTarget = { kind: 'subversion', versionId: props.versionId };
  const entries = list.page?.items ?? [];
  const pending = hasPending(props.id, target);
  function move(index: number, direction: number) {
    const ids = entries.map((entry) => entry.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    void actions.perform('reorder', target, { ids });
  }
  return <section className="roadmap-subversions" aria-label="Subversions">
    <div className="roadmap-collection-heading"><h3>Subversions</h3>
      <button type="button" disabled={props.disabled} onClick={() => props.edit({ title: 'New subversion', target,
        initial: { number: '', title: '', description: '', notes: '', status: 'open' }, create: true })}>Add subversion</button></div>
    {(list.error || actions.error) && <p className="project-error" role="alert">{list.error || actions.error}</p>}
    {props.disabled && <p className="project-message">Save or cancel the current edit before changing another entry.</p>}
    {list.loading && <p role="status">Loading subversions…</p>}
    {pending && <button type="button" disabled={props.disabled} onClick={() => void actions.perform('reorder', target, {})}>Confirm original order change</button>}
    {entries.map((sub, index) => <div className="roadmap-subversion-row" key={sub.id}>
      <Subversion {...props} sub={sub} />
      <div className="roadmap-order-actions" role="group" aria-label={`Order ${sub.number}`}><span>Order</span>
        <button type="button" disabled={props.disabled || pending || !!list.page?.nextCursor || entries.length > 500 || index === 0} onClick={() => move(index, -1)} aria-label={`Move ${sub.number} up`}>↑</button>
        <button type="button" disabled={props.disabled || pending || !!list.page?.nextCursor || entries.length > 500 || index === entries.length - 1} onClick={() => move(index, 1)} aria-label={`Move ${sub.number} down`}>↓</button>
      </div>
    </div>)}
    {!list.loading && list.page && entries.length === 0 && <p className="project-message">No subversions yet.</p>}
    {list.page?.nextCursor && <button type="button" disabled={props.disabled || list.busy} onClick={() => void list.more()}>{list.busy ? 'Loading…' : 'More subversions'}</button>}
    {list.page?.nextCursor && <p className="project-message">Load the complete collection before changing its order.</p>}
  </section>;
}
