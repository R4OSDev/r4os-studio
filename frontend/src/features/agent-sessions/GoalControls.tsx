import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { FormEvent, ReactNode } from 'react';
import type { AgentRun } from '../../../../shared/agent-sessions';
import { busyRun } from './api';
import { Icon } from '../../app/Icon';
import type { useGoal } from './useGoal';

type Control = ReturnType<typeof useGoal>;
const whitespace = new Set([9, 10, 11, 12, 13, 32, 133, 160, 5760, ...Array.from({ length: 11 }, (_, index) => 8192 + index), 8232, 8233, 8239, 8287, 12288]);
export function normalizeGoal(value: string) {
  let first = 0, last = value.length;
  while (first < last && whitespace.has(value.charCodeAt(first))) first++;
  while (last > first && whitespace.has(value.charCodeAt(last - 1))) last--;
  return value.slice(first, last);
}

export function goalLabel(control: Control) {
  if (control.checking) return 'Checking…';
  if (!control.available) return 'Unavailable';
  if (control.pending) return ({ save: 'Saving…', play: 'Starting…', pause: 'Pausing…', stop: 'Stopping…' })[control.pending.action];
  if (control.goal?.phase === 'unknown') return 'Unconfirmed';
  if (control.goal?.phase === 'pausing') return 'Pausing…';
  const status = control.goal?.goal?.status;
  if (status === 'paused' && control.goal?.lastIntent === 'stop') return 'Stopped';
  return status ? ({ active: 'Active', paused: 'Paused', blocked: 'Blocked', usageLimited: 'Usage limit', budgetLimited: 'Budget limit', complete: 'Complete' })[status] : 'Ready';
}

export function GoalControls({ control, run, disabled, editor, openEditor, stopRun, inputBusy = false, runtime }: {
  control: Control; run?: AgentRun | null; disabled: boolean; editor: boolean; openEditor: () => void; stopRun: () => Promise<void>; inputBusy?: boolean; runtime?: ReactNode;
}) {
  const group = useRef<HTMLDivElement>(null), textButton = useRef<HTMLButtonElement>(null);
  const state = control.goal, status = state?.goal?.status;
  const running = busyRun(run?.state);
  const liveReady = control.liveExecution && run?.goalControlSupport;
  const active = (running && !liveReady) || (status === 'active' && state?.phase !== 'unknown');
  const ready = !disabled && control.available && !control.changing && !editor;
  const confirmed = state?.phase === 'idle' || state?.phase === 'pausing';
  const stopped = confirmed && state?.lastIntent === 'stop' && status !== 'active';
  const canStopRun = busyRun(run?.state);
  useEffect(() => { if (ready && document.activeElement === group.current) textButton.current?.focus(); }, [ready]);
  return <div className="agent-goal" role="group" aria-label="Goal controls" aria-busy={control.changing} ref={group} tabIndex={-1}>
    <div className="agent-goal-top">
      <div className="agent-goal-buttons">
        <button type="button" aria-label="Play goal" title={running ? (liveReady ? 'Activate this Goal in the current run' : 'Wait for a ready compatible worker') : 'Start or resume this Goal'} aria-pressed={!!(confirmed && status === 'active')}
          disabled={!ready || inputBusy || active || state?.phase !== 'idle' || !control.execution}
          onClick={() => state?.goal ? void control.perform('play') : openEditor()}><Icon name="play" /></button>
        <button type="button" aria-label="Pause goal" title="Pause after the current turn" aria-pressed={!!(confirmed && status === 'paused' && !stopped)}
          disabled={!ready || ((!state?.goal || status !== 'active') && state?.phase !== 'unknown')} onClick={() => void control.perform('pause')}><Icon name="pause" /></button>
        <button type="button" aria-label="Stop goal" title="Pause the Goal and interrupt its run" aria-pressed={!!stopped}
          disabled={disabled || (!canStopRun && (!ready || (!state?.goal && state?.phase !== 'unknown') || (status === 'complete' && state?.phase !== 'unknown')))}
          onClick={() => { if (canStopRun) void stopRun(); else void control.perform('stop'); }}><Icon name="stop" /></button>
      </div>
      {runtime}
      <span className="agent-goal-state" role="status" title={state?.phase === 'pausing' ? 'Pausing after current turn' : goalLabel(control)}>{goalLabel(control)}</span>
      <span className="agent-goal-caption">GOAL</span>
    </div>
    <button type="button" className="agent-goal-text" aria-label="Edit goal" title={state?.goal?.objective ?? 'Set a goal'} ref={textButton}
      disabled={disabled || inputBusy || !control.available || control.changing} onClick={openEditor}>{state?.goal?.objective ?? 'Set a goal'}</button>
  </div>;
}

export function GoalEditor({ control, run, stopRun, close, dirtyChanged }: {
  control: Control; run?: AgentRun | null; stopRun: () => Promise<void>; close: () => void; dirtyChanged: (value: boolean) => void;
}) {
  const activeRun = busyRun(run?.state);
  const activeOrdinaryRun = activeRun && run?.mode !== 'goal' && (!control.liveExecution || !run?.goalControlSupport);
  const activeGoal = control.goal?.goal?.status === 'active';
  const saved = control.goal?.goal?.objective ?? '';
  const [baseline, setBaseline] = useState({ revision: control.goal?.revision ?? 0, text: saved });
  const [text, setText] = useState(() => { try { return sessionStorage.getItem(control.draftKey) ?? saved; } catch { return saved; } });
  const dialog = useRef<HTMLDialogElement>(null);
  const normalized = normalizeGoal(text), count = Array.from(normalized).length;
  const invalid = count > 4000 || Array.from(normalized).some((character) => character === '\0' || (character.charCodeAt(0) >= 0xd800 && character.charCodeAt(0) <= 0xdfff && character.length === 1));
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal(); element.querySelector('textarea')?.focus();
    return () => {
      element.close();
      if (opener instanceof HTMLElement && opener.isConnected) {
        if (opener.matches(':disabled')) opener.closest<HTMLElement>('.agent-goal')?.focus(); else opener.focus();
      }
    };
  }, []);
  useEffect(() => { dirtyChanged(text !== baseline.text); return () => dirtyChanged(false); }, [text, baseline.text, dirtyChanged]);
  const conflict = control.goal && control.goal.revision !== baseline.revision && !control.changing;
  function discard() { if (control.posting) return; sessionStorage.removeItem(control.draftKey); close(); }
  async function save(event: FormEvent) {
    event.preventDefault(); event.stopPropagation();
    if (invalid || control.changing || activeOrdinaryRun || activeGoal || control.goal?.phase === 'unknown') return;
    if (await control.perform('save', normalized, baseline.revision)) close();
  }
  return createPortal(<dialog className="project-dialog agent-goal-dialog" ref={dialog} aria-labelledby="goal-editor-title"
    onCancel={(event) => { event.preventDefault(); discard(); }}>
    <form onSubmit={(event) => void save(event)}>
      <header className="project-dialog-header"><h2 id="goal-editor-title">Edit goal</h2></header>
      <label htmlFor="goal-objective">Goal</label>
      <textarea id="goal-objective" rows={6} maxLength={16000} value={text} disabled={control.posting} onChange={(event) => {
        setText(event.target.value); try { sessionStorage.setItem(control.draftKey, event.target.value); } catch { /* Submission checks durable storage. */ }
      }} aria-describedby="goal-editor-help goal-editor-count" aria-invalid={invalid} />
      <div className="agent-goal-editor-help"><p id="goal-editor-help">Save keeps the Goal paused. Play activates it in the current ready run. Queued messages take priority after the current turn.</p><span id="goal-editor-count">{count} / 4000</span></div>
      {activeOrdinaryRun && <p className="project-dialog-status">This worker is not ready for live Goal control. Your draft is preserved.</p>}
      {activeGoal && <p className="project-dialog-status">Pause the active Goal before changing its text.</p>}
      {control.goal?.phase === 'unknown' && <p className="project-dialog-error">Pause or Stop the unconfirmed Goal before editing it.</p>}
      {invalid && <p className="project-dialog-error" role="alert">Enter valid text with at most 4000 Unicode characters.</p>}
      {conflict && <div className="agent-goal-conflict"><p>The saved Goal changed. Your draft is preserved.</p><p className="agent-goal-saved">{saved || 'No saved Goal'}</p>
        <button type="button" onClick={() => setBaseline({ revision: control.goal!.revision, text: saved })}>Review saved goal</button></div>}
      {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
      <footer className="project-actions">{activeGoal && <button type="button" disabled={control.changing} onClick={() => void control.perform('pause')}>Pause goal</button>}{activeRun && <button type="button" onClick={() => void stopRun()}>Stop current run</button>}<button type="button" disabled={control.posting} onClick={discard}>Discard</button>
        <button className="project-primary" disabled={invalid || !!conflict || control.changing || activeOrdinaryRun || activeGoal || control.goal?.phase === 'unknown'}>{control.posting ? 'Saving…' : 'Save'}</button></footer>
    </form>
  </dialog>, document.body);
}
