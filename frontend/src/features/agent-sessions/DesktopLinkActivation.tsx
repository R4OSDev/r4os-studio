import { useState } from 'react';
import type { Project } from '../../../../shared/projects';
import type { DevelopmentJob, DevelopmentOptions, DevelopmentRunInput, DevelopmentSettings } from '../../../../shared/project-development';
import { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
import { DevelopmentCard } from './DevelopmentCard';

type Saved = { input: DevelopmentRunInput; jobId?: string };
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;

export function DesktopLinkActivation({ projectId, sourceJobId, deploymentId, token }: {
  projectId: string; sourceJobId: string; deploymentId: string; token: string;
}) {
  const key = `studio.desktop-link:${projectId}:${sourceJobId}`;
  const [saved, setSaved] = useState<Saved | null>(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(key) ?? 'null') as Saved | null;
      return value?.input.deploymentId === deploymentId && value.input.desktopLink === true && uuid.test(value.input.requestId)
        && Number.isSafeInteger(value.input.projectRevision) && Number.isSafeInteger(value.input.settingsRevision)
        && (!value.jobId || uuid.test(value.jobId)) ? value : null;
    } catch { return null; }
  });
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  function accepted(original: Saved, job: DevelopmentJob) {
    const value = { ...original, jobId: job.id };
    sessionStorage.setItem(key, JSON.stringify(value)); setSaved(value);
  }
  async function activate() {
    if (busy || saved?.jobId) return;
    setBusy(true); setError('');
    let original = saved;
    const first = original === null;
    try {
      if (!original) {
        const [project, settings, options] = await Promise.all([
          projectRequest<{ project: Project }>(`/${projectId}`),
          projectRequest<DevelopmentSettings>(`/${projectId}/development/settings`),
          projectRequest<DevelopmentOptions>(`/${projectId}/development/options`),
        ]);
        if (!options.desktopLinkActivation?.available) throw new Error(options.desktopLinkActivation?.reason ?? 'Native desktop link activation is unavailable.');
        if (settings.arguments) throw new Error('Clear Run & Test arguments before activating the published desktop link.');
        original = { input: { requestId: projectRequestId(), projectRevision: project.project.revision,
          settingsRevision: settings.revision, deploymentId, desktopLink: true } };
        sessionStorage.setItem(key, JSON.stringify(original)); setSaved(original);
      } else {
        // A lost reply is read before any idempotent resubmission. Keep the
        // original body and identity; never choose a newer deployment.
        try {
          const response = await projectRequest<{ job: DevelopmentJob }>(`/${projectId}/development/jobs/requests/${original.input.requestId}`);
          accepted(original, response.job); return;
        } catch (e) {
          if (!(e instanceof ProjectRequestError) || e.status !== 404) throw e;
        }
      }
      const response = await projectRequest<{ job: DevelopmentJob }>(`/${projectId}/development/executions`, token, 'POST', original.input);
      accepted(original, response.job);
    } catch (e) {
      if (original && first && e instanceof ProjectRequestError && [400, 401, 403, 409, 429].includes(e.status)) {
        try {
          const response = await projectRequest<{ job: DevelopmentJob }>(`/${projectId}/development/jobs/requests/${original.input.requestId}`);
          accepted(original, response.job);
        } catch (readError) {
          // Only the completed first rejection plus exact no-admission read
          // permits discarding this draft. Uncertain prior requests stay bound.
          if (readError instanceof ProjectRequestError && readError.status === 404) {
            sessionStorage.removeItem(key); setSaved(null);
          }
        }
      }
      setError((e as Error).message);
    } finally { setBusy(false); }
  }
  return <div className="development-desktop-publication">
    {!saved?.jobId && <><p>Activate this verified shortcut through the native Desktop link path. Requires a new native-link-v1 deployment and compatible guest.</p>
      <button type="button" disabled={busy} onClick={() => void activate()}>{busy ? 'Submitting…' : saved ? 'Read or retry original link request' : 'Run desktop link'}</button></>}
    {error && <p className="agent-error" role="alert">{error}</p>}
    {saved?.jobId && <DevelopmentCard projectId={projectId} jobId={saved.jobId} token={token} desktopAction={false} />}
  </div>;
}
