import { useState } from 'react';
import type { Project } from '../../../../shared/projects';
import type { DevelopmentDeployInput, DevelopmentJob, DevelopmentOptions, DevelopmentSettings } from '../../../../shared/project-development';
import { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
import { DevelopmentCard } from './DevelopmentCard';

type Saved = { input: DevelopmentDeployInput; jobId?: string };
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;

export function DesktopDeployment({ projectId, sourceJobId, artifactId, token }: {
  projectId: string; sourceJobId: string; artifactId: string; token: string;
}) {
  const key = `studio.desktop-deploy:${projectId}:${sourceJobId}`;
  const [saved, setSaved] = useState<Saved | null>(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(key) ?? 'null') as Saved | null;
      return value?.input.artifactId === artifactId && value.input.desktopShortcut === true && uuid.test(value.input.requestId)
        && Number.isSafeInteger(value.input.projectRevision) && Number.isSafeInteger(value.input.settingsRevision)
        && (!value.jobId || uuid.test(value.jobId)) ? value : null;
    } catch { return null; }
  });
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [target, setTarget] = useState('');

  async function deploy() {
    if (busy || saved?.jobId) return;
    setBusy(true); setError('');
    let firstSubmission = false;
    try {
      let original = saved;
      if (!original) {
        const [project, settings, options] = await Promise.all([
          projectRequest<{ project: Project }>(`/${projectId}`),
          projectRequest<DevelopmentSettings>(`/${projectId}/development/settings`),
          projectRequest<DevelopmentOptions>(`/${projectId}/development/options`),
        ]);
        if (!options.deploy.available) throw new Error(options.deploy.reason ?? 'Deployment is unavailable.');
        if (options.desktopShortcutVersion !== 1) throw new Error('Desktop publication requires the current development coordinator. Wait for its active jobs to finish.');
        setTarget(options.assignedVm?.name ?? 'Assigned VM');
        original = { input: { requestId: projectRequestId(), projectRevision: project.project.revision,
          settingsRevision: settings.revision, artifactId, desktopShortcut: true } };
        // Save the complete original body before sending. Retry never picks a newer build or revision.
        sessionStorage.setItem(key, JSON.stringify(original)); setSaved(original);
        firstSubmission = true;
      }
      const response = await projectRequest<{ job: DevelopmentJob }>(`/${projectId}/development/deployments`, token, 'POST', original.input);
      const accepted = { ...original, jobId: response.job.id };
      setSaved(accepted);
      sessionStorage.setItem(key, JSON.stringify(accepted));
    } catch (e) {
      if (firstSubmission && e instanceof ProjectRequestError && [400, 401, 403, 409, 429].includes(e.status)) {
        // A confirmed first admission rejection has no earlier uncertain request to preserve.
        sessionStorage.removeItem(key); setSaved(null);
      }
      setError((e as Error).message);
    }
    finally { setBusy(false); }
  }

  return <div className="development-desktop-publication">
    <p>Desktop publication creates the link. Native launch through this link is unavailable until R4OS provides a recoverable activation receipt.</p>
    {!saved?.jobId && <><p>Create or update this project’s desktop shortcut on its assigned VM using this build.</p>
      <button type="button" disabled={busy} onClick={() => void deploy()}>{busy ? 'Submitting…' : saved ? 'Retry same desktop deployment' : 'Deploy to desktop'}</button></>}
    {target && <p>Target: {target}</p>}
    {error && <p className="agent-error" role="alert">{error}</p>}
    {saved?.jobId && <DevelopmentCard projectId={projectId} jobId={saved.jobId} token={token} desktopAction={false} />}
  </div>;
}
