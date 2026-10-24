import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { Project } from '../../../../shared/projects';
import type { DevelopmentOptions, DevelopmentSettings } from '../../../../shared/project-development';
import { projectRequest, ProjectRequestError } from './api';
import { ProjectField } from './ProjectField';

export function RunTestSettings({ id, token, dirtyChanged, busyChanged }: {
  id: string; token: string; dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [draft, setDraft] = useState<DevelopmentSettings | null>(null), [saved, setSaved] = useState<DevelopmentSettings | null>(null);
  const [project, setProject] = useState<Project | null>(null), [options, setOptions] = useState<DevelopmentOptions | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [conflict, setConflict] = useState(false), [epoch, setEpoch] = useState(0);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved), base = `/${id}/development`;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      projectRequest<DevelopmentSettings>(base + '/settings', '', 'GET', undefined, controller.signal),
      projectRequest<{ project: Project }>(`/${id}`, '', 'GET', undefined, controller.signal),
      projectRequest<DevelopmentOptions>(base + '/options', '', 'GET', undefined, controller.signal),
    ]).then(([settings, p, o]) => { if (!controller.signal.aborted) { setDraft(settings); setSaved(settings); setProject(p.project); setOptions(o); setError(''); setConflict(false); } })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [base, id, epoch]);
  const patch = (value: Partial<DevelopmentSettings>) => { setDraft((old) => old ? { ...old, ...value } : old); setNotice(''); };
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!draft || busy) return; setBusy(true); setError(''); setNotice('');
    try {
      const result = await projectRequest<DevelopmentSettings>(base + '/settings', token, 'PATCH', draft);
      setDraft(result); setSaved(result); setNotice('Saved.');
    } catch (e) { setError((e as Error).message); setConflict((e as ProjectRequestError).status === 409); }
    finally { setBusy(false); }
  }
  const files = draft?.outputFiles ?? [];
  const filePatch = (index: number, value: Partial<DevelopmentSettings['outputFiles'][number]>) => patch({ outputFiles: files.map((f, i) => i === index ? { ...f, ...value } : f) });
  return <form className="project-settings run-test-settings" aria-label="Run and test settings" onSubmit={(e) => void submit(e)}>
    <h2>Run &amp; Test</h2>
    {options && project && <dl className="development-target"><div><dt>Entry</dt><dd>Project module · {project.template}</dd></div><div><dt>Build</dt><dd>{project.language} · SDK {project.pins.sdk.version} · Zig {project.pins.zig.version}</dd></div><div><dt>Target</dt><dd>{options.assignedVm ? `${options.assignedVm.name} · R4OS ${options.assignedVm.imageId.replace('-full', '')}` : 'No VM assigned'}</dd></div></dl>}
    {options && !options.execute.available && <p className="project-message">{options.execute.reason}</p>}
    {!draft && !error && <p role="status">Loading settings…</p>}
    {draft && <fieldset className="project-fields" disabled={busy}>
      <ProjectField id="run-arguments" label="Arguments (UTF-8: 127 bytes, services 95)"><input id="run-arguments" maxLength={project?.template === 'service' ? 95 : 1024} value={draft.arguments} onChange={(e) => patch({ arguments: e.target.value })} /></ProjectField>
      <div className="project-form-row">
        <ProjectField id="run-cwd" label="Working directory"><input id="run-cwd" value="Deployment directory" readOnly /></ProjectField>
        <ProjectField id="run-timeout" label="Time limit (seconds)"><input id="run-timeout" type="number" min={1} max={300} required value={draft.timeoutSeconds} onChange={(e) => patch({ timeoutSeconds: Number(e.target.value) })} /></ProjectField>
      </div>
      <h3>Checks</h3>
      <ProjectField id="run-exit" label="Expected exit code"><input id="run-exit" type="number" min={-2147483648} max={2147483647} placeholder="Any" value={draft.expectedExitCode ?? ''} onChange={(e) => patch({ expectedExitCode: e.target.value === '' ? null : Number(e.target.value) })} /></ProjectField>
      <ProjectField id="run-output" label="Expected console output"><textarea id="run-output" rows={3} value={draft.outputContains.join('\n')} onChange={(e) => patch({ outputContains: e.target.value.split('\n').filter(Boolean) })} /></ProjectField>
      {project?.template === 'service' && <ProjectField id="run-service" label="Expected self-test response"><input id="run-service" maxLength={256} value={draft.serviceResponseContains ?? ''} onChange={(e) => patch({ serviceResponseContains: e.target.value || null })} /></ProjectField>}
      {project?.template === 'desktop' && <ProjectField id="run-visual" label="Visual criteria"><textarea id="run-visual" rows={3} maxLength={1024} value={draft.visualCriteria} onChange={(e) => patch({ visualCriteria: e.target.value })} /></ProjectField>}
      <div className="development-file-heading"><h3>Output files</h3><button type="button" disabled={files.length >= 8} onClick={() => patch({ outputFiles: [...files, { name: '', contains: null, sha256: null }] })}>Add file</button></div>
      {files.map((file, index) => <fieldset className="development-file" key={index}><legend>File {index + 1}</legend>
        <ProjectField id={`run-file-${index}`} label="Name"><input id={`run-file-${index}`} required pattern="[A-Z0-9_]{1,8}\.[A-Z0-9_]{1,3}" maxLength={12} placeholder="RESULT.TXT" value={file.name} onChange={(e) => filePatch(index, { name: e.target.value.toUpperCase() })} /></ProjectField>
        <ProjectField id={`run-file-text-${index}`} label="Expected text"><input id={`run-file-text-${index}`} maxLength={1024} value={file.contains ?? ''} onChange={(e) => filePatch(index, { contains: e.target.value || null })} /></ProjectField>
        <ProjectField id={`run-file-hash-${index}`} label="Expected SHA-256"><input id={`run-file-hash-${index}`} pattern="[a-f0-9]{64}" value={file.sha256 ?? ''} onChange={(e) => filePatch(index, { sha256: e.target.value || null })} /></ProjectField>
        <button type="button" onClick={() => patch({ outputFiles: files.filter((_, i) => i !== index) })}>Remove file</button>
      </fieldset>)}
    </fieldset>}
    {error && <p className="project-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {error && <button type="button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Reload saved settings and discard these changes?')) setEpoch((v) => v + 1); }}>Reload settings</button>}
    <div className="project-actions"><button type="button" disabled={busy || !dirty} onClick={() => { setDraft(saved); setError(''); setNotice(''); setConflict(false); }}>Cancel</button><button type="submit" className="project-primary" disabled={busy || !dirty || !draft || conflict}>{busy ? 'Saving…' : 'Save changes'}</button></div>
  </form>;
}
