import { ProjectField } from './ProjectField';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { Project, ProjectOptions, ProjectUpdate } from '../../../../shared/projects';
import { projectRequest, ProjectRequestError } from './api';

export type ProjectSettingsView = 'General' | 'Virtual machine' | 'Run & Test';
export function ProjectSettings({ id, view, token, dirtyChanged, busyChanged, saved }: {
  id: string; view: ProjectSettingsView; token: string; dirtyChanged: (value: boolean) => void;
  busyChanged: (value: boolean) => void;
  saved: () => Promise<void>;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [name, setName] = useState(''), [description, setDescription] = useState(''), [vmId, setVmId] = useState('');
  const [vms, setVms] = useState<Pick<ProjectOptions, 'vms' | 'vmsAvailable'>>({ vms: [], vmsAvailable: true });
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false), [conflict, setConflict] = useState(false), [epoch, setEpoch] = useState(0);
  const dirty = !!project && (view === 'General' ? name !== project.name || description !== project.description : (vmId || null) !== project.vmId);
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<{ project: Project }>(`/${id}`, '', 'GET', undefined, controller.signal)
      .then(({ project: value }) => {
        if (controller.signal.aborted) return;
        setProject(value); setName(value.name); setDescription(value.description); setVmId(value.vmId ?? ''); setConflict(false); setError('');
      }).catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    if (view === 'Virtual machine') void projectRequest<Pick<ProjectOptions, 'vms' | 'vmsAvailable'>>('/vms', '', 'GET', undefined, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setVms(value); })
      .catch(() => { if (!controller.signal.aborted) setVms({ vms: [], vmsAvailable: false }); });
    return () => controller.abort();
  }, [id, view, epoch]);

  async function submit(event: FormEvent) {
    event.preventDefault(); if (!project || busy) return;
    setBusy(true); setError(''); setNotice('');
    const input: ProjectUpdate = { revision: project.revision, ...(view === 'General' ? { name: name.trim(), description } : { vmId: vmId || null }) };
    try {
      const result = await projectRequest<{ project: Project }>(`/${id}`, token, 'PATCH', input);
      setProject(result.project); setName(result.project.name); setDescription(result.project.description); setVmId(result.project.vmId ?? '');
      setNotice('Saved.'); await saved();
    } catch (cause) { setError((cause as Error).message); setConflict((cause as ProjectRequestError).status === 409); }
    finally { setBusy(false); }
  }
  function cancel() {
    if (!project) return;
    setName(project.name); setDescription(project.description); setVmId(project.vmId ?? ''); setError(''); setNotice('');
  }
  return <form className="project-settings" onSubmit={(event) => void submit(event)} aria-label={`Project ${view} settings`}>
    <h2>{view}</h2>
    {!project && !error && <p className="project-message" role="status">Loading settings…</p>}
    {project && <fieldset className="project-fields" disabled={busy}>
      {view === 'General' ? <>
        <ProjectField id="settings-name" label="Name"><input id="settings-name" required maxLength={120} value={name} onChange={(event) => { setName(event.target.value); setNotice(''); }} /></ProjectField>
        <ProjectField id="settings-description" label="Description"><textarea id="settings-description" rows={4} maxLength={4000} value={description} onChange={(event) => { setDescription(event.target.value); setNotice(''); }} /></ProjectField>
      </> : <>
        <ProjectField id="settings-vm" label="Virtual machine"><select id="settings-vm" value={vmId} onChange={(event) => { setVmId(event.target.value); setNotice(''); }}>
          <option value="">None</option>{vmId && !vms.vms.some((vm) => vm.id === vmId) && <option value={vmId}>Unavailable virtual machine</option>}
          {vms.vms.map((vm) => <option key={vm.id} value={vm.id}>{vm.name}</option>)}
        </select></ProjectField>
        {!vms.vmsAvailable && <p className="project-message" role="status">Virtual machines could not be loaded.</p>}
      </>}
    </fieldset>}
    {error && <p className="project-error" role="alert">{error}</p>}{notice && <p className="project-message" role="status">{notice}</p>}
    {conflict && <button type="button" className="project-reload" onClick={() => setEpoch((value) => value + 1)}>Reload settings</button>}
    <div className="project-actions"><button type="button" disabled={busy || !dirty} onClick={cancel}>Cancel</button>
      <button className="project-primary" type="submit" disabled={busy || !dirty || !project || conflict}>{busy ? 'Saving…' : 'Save changes'}</button></div>
  </form>;
}
