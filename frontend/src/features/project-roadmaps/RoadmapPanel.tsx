import { useEffect, useRef, useState } from 'react';
import type { RoadmapBinding, RoadmapMutationResult, RoadmapProgress, RoadmapVersionHeader } from '../../../../shared/project-roadmaps';
import { ProjectRequestError, projectRequestId } from '../projects/api';
import { RoadmapForm } from './RoadmapForm';
import type { RoadmapModel } from './useRoadmap';
import { mutate, roadmapRequest } from './api';
import { versionStatusLabels } from './model';
import './styles.css';

export function Progress({ progress }: { progress: RoadmapProgress }) {
  return <dl className="roadmap-progress">{(['tasks', 'acceptances'] as const).map((kind) => <div key={kind}>
    <dt>{kind === 'tasks' ? 'Tasks' : 'Acceptance items'}</dt>
    <dd>{progress[kind].done} / {progress[kind].total} done{progress[kind].discarded ? ` · ${progress[kind].discarded} discarded` : ''}</dd>
  </div>)}</dl>;
}

function VersionDialog({ close, children }: { close: () => void; children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal(); element.querySelector<HTMLInputElement>('input')?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  return <dialog ref={dialog} className="project-dialog" aria-labelledby="roadmap-new-version-title"
    onCancel={(event) => { event.preventDefault(); close(); }}>
    <header className="project-dialog-header"><h2 id="roadmap-new-version-title">New Version</h2></header>
    {children}
  </dialog>;
}

export function RoadmapPanel({ id, token, model, selectedVersionId, creating, closeCreate, created, dirty, dirtyChanged, busyChanged }: {
  id: string; token: string; model: RoadmapModel; selectedVersionId?: string; creating: boolean;
  closeCreate: () => void; created: (versionId: string) => void;
  dirty: boolean; dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [actionBusy, setActionBusy] = useState(false), [actionError, setActionError] = useState('');
  const state = model.overview;
  const [formBusy, setFormBusy] = useState(false);
  useEffect(() => { busyChanged(actionBusy || formBusy); return () => busyChanged(false); }, [actionBusy, formBusy, busyChanged]);
  const refresh = () => { if (!dirty || window.confirm('Discard unsaved roadmap changes and refresh?')) model.reload(); };
  async function initialize() {
    const key = 'studio.roadmap.initialize.' + id;
    setActionBusy(true); setActionError('');
    try {
      let requestId = sessionStorage.getItem(key);
      if (!requestId) { requestId = projectRequestId(); sessionStorage.setItem(key, requestId); }
      await roadmapRequest(id, '/initialize', token, 'POST', { requestId });
      sessionStorage.removeItem(key); model.reload();
    } catch (cause) { setActionError((cause as Error).message); }
    finally { setActionBusy(false); }
  }
  async function selectCurrent(binding: RoadmapBinding, version: RoadmapVersionHeader) {
    if (dirty || actionBusy) return;
    const key = `studio.roadmap.current.${id}.${version.id}`;
    setActionBusy(true); setActionError('');
    try {
      const original = sessionStorage.getItem(key);
      const body = original ? JSON.parse(original) : { requestId: projectRequestId(), expectedRevision: binding.revision,
        currentVersionId: binding.currentVersionId, action: 'set_current', target: { kind: 'version', id: version.id }, input: {} };
      sessionStorage.setItem(key, JSON.stringify(body));
      await mutate(id, token, body); sessionStorage.removeItem(key); model.reload();
    } catch (cause) {
      const failure = cause as ProjectRequestError;
      if (failure.status >= 400 && failure.status < 500) sessionStorage.removeItem(key);
      setActionError(failure.message);
    }
    finally { setActionBusy(false); }
  }
  const onSaved = (result: RoadmapMutationResult) => {
    dirtyChanged(false);
    if (creating && 'id' in result.entity) created(result.entity.id);
    model.reload();
  };
  let pendingSelection = false;
  try { pendingSelection = !!model.version && !!sessionStorage.getItem(`studio.roadmap.current.${id}.${model.version.id}`); }
  catch { /* Saving reports unavailable browser storage before sending. */ }
  return <section className="roadmap" aria-label="Project roadmap">
    <div className="roadmap-toolbar"><h2>Roadmap</h2><button type="button" disabled={actionBusy || formBusy} onClick={refresh}>Refresh</button></div>
    {model.loading && <p role="status">Loading roadmap…</p>}
    {(model.error || actionError) && <p className="project-error" role="alert">{model.error || actionError}</p>}
    {state && !state.exists && <div className="roadmap-card"><h3>No roadmap yet</h3>
      <p>Initialize one shared roadmap for this project, starting with an empty 0.1.X version.</p>
      <button type="button" className="roadmap-primary" disabled={actionBusy} onClick={() => void initialize()}>{actionBusy ? 'Initializing…' : 'Initialize roadmap'}</button></div>}
    {state?.exists && <>
      <p className="roadmap-shared-note">Shared by all sessions of this project. Selecting a version only changes this view.</p>
      {creating ? <VersionDialog close={() => { if (!formBusy) closeCreate(); }}>
        <RoadmapForm key={'new:' + model.epoch} id={id} token={token} binding={{ revision: state.roadmap.revision, currentVersionId: state.roadmap.currentVersionId }}
          target={{ kind: 'version' }} initial={{ number: '', title: 'New', vision: '', notes: '', status: 'open' }} create
          saved={onSaved} cancel={closeCreate} dirtyChanged={dirtyChanged} busyChanged={setFormBusy} />
      </VersionDialog> : !selectedVersionId ? <div className="roadmap-card"><h3>Overview</h3><Progress progress={state.roadmap.progress} />
        <RoadmapForm key={state.roadmap.id + ':' + model.epoch} id={id} token={token}
          binding={{ revision: state.roadmap.revision, currentVersionId: state.roadmap.currentVersionId }}
          target={{ kind: 'roadmap', id: state.roadmap.id }} initial={{ description: state.roadmap.description, notes: state.roadmap.notes }}
          saved={onSaved} cancel={model.reload} dirtyChanged={dirtyChanged} busyChanged={setFormBusy} />
      </div> : model.version && <div className="roadmap-card">
        <div className="roadmap-version-heading"><h3>{model.version.number} · {model.version.title}</h3>
          <span className="roadmap-status">{versionStatusLabels[model.version.status]}{state.roadmap.currentVersionId === model.version.id ? ' · Current' : ''}</span></div>
        <Progress progress={model.version.progress} />
        {(state.roadmap.currentVersionId !== model.version.id || pendingSelection) && <button type="button" className="roadmap-set-current" disabled={dirty || actionBusy || formBusy}
          onClick={() => void selectCurrent(state.roadmap, model.version!)}>{pendingSelection ? 'Confirm original selection' : 'Make current version'}</button>}
        <RoadmapForm key={model.version.id + ':' + model.epoch} id={id} token={token}
          binding={{ revision: state.roadmap.revision, currentVersionId: state.roadmap.currentVersionId }}
          target={{ kind: 'version', id: model.version.id }} initial={{ number: model.version.number, title: model.version.title,
            status: model.version.status, vision: model.version.vision, notes: model.version.notes }}
          saved={onSaved} cancel={model.reload} dirtyChanged={dirtyChanged} busyChanged={setFormBusy} />
        <p className="roadmap-subversion-count">{model.version.subversionCount} subversions</p>
      </div>}
    </>}
  </section>;
}
