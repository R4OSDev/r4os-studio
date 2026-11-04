import { useEffect, useRef, useState } from 'react';
import type { SkillDetail, SkillSourceConfiguration, SkillSourceJob, SkillRuntimeStatus } from '../../../../shared/skills';
import type { GitHubConnection } from '../../../../shared/github-connections';
import { loadConnections } from '../github-connections/api';
import { projectRequestId } from '../projects/api';
import { request } from './api';

const terminal = new Set(['complete', 'failed', 'cancelled']);
const empty = { repository: '', ref: '', skillPath: '', recipe: null, connectionId: null } as SkillSourceConfiguration;
type Intent = { kind: 'configure'; requestId: string; revision: number; source: SkillSourceConfiguration | null }
  | { kind: 'activate' | 'update'; requestId: string };

export function SkillSourcePanel({ detail, token, disabled, changed, draftChanged, workingChanged, refreshAuth }: {
  detail: SkillDetail; token: string; disabled: boolean; changed: (value: SkillDetail) => void;
  draftChanged: (value: boolean) => void; workingChanged: (value: boolean) => void;
  refreshAuth: () => Promise<void>;
}) {
  const id = detail.skill.id, key = 'studio-skill-source:' + id;
  const [fields, setFields] = useState<SkillSourceConfiguration>(detail.source?.configuration ?? empty);
  const [connections, setConnections] = useState<GitHubConnection[]>([]);
  const [job, setJob] = useState<SkillSourceJob>(), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const runtimeKey = id + ':' + (detail.source?.active?.packageHash ?? '');
  const hasRuntime = !!detail.source?.active?.runtime;
  const [runtimeState, setRuntime] = useState<{ key: string; value: SkillRuntimeStatus }>();
  const runtime = hasRuntime && runtimeState?.key === runtimeKey ? runtimeState.value : undefined;
  useEffect(() => {
    let alive = true;
    if (hasRuntime) void request<SkillRuntimeStatus>('GET', '/' + id + '/source/runtime')
      .then(value => { if (alive) setRuntime({ key: runtimeKey, value }); })
      .catch(() => { if (alive) setRuntime({ key: runtimeKey, value: { ready: false, reason: 'Installation proof could not be loaded. Refresh access to check again.' } }); });
    return () => { alive = false; };
  }, [id, runtimeKey, hasRuntime, detail.source?.updatedAt]);
  const [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState<Intent | undefined>(() => {
    try { const value = sessionStorage.getItem(key); return value ? JSON.parse(value) as Intent : undefined; }
    catch { return undefined; }
  });
  const lifetime = useRef(0);
  const uncertainId = uncertain?.requestId, uncertainKind = uncertain?.kind;
  const pending = !!(job?.requestId ?? detail.source?.lastRequestId) && !terminal.has(job?.phase ?? detail.source?.status ?? 'queued');
  const dirty = JSON.stringify(fields) !== JSON.stringify(detail.source?.configuration ?? empty);
  const locked = disabled || busy || pending || !!uncertain;
  useEffect(() => { draftChanged(dirty); return () => draftChanged(false); }, [dirty, draftChanged]);
  useEffect(() => { workingChanged(busy || pending || !!uncertain); return () => workingChanged(false); }, [busy, pending, uncertain, workingChanged]);
  useEffect(() => {
    let active = true;
    const epoch = lifetime.current;
    void loadConnections().then(value => { if (active) setConnections(value.connections); }).catch(() => {});
    return () => { active = false; lifetime.current = epoch + 1; };
  }, [key]);
  useEffect(() => {
    if (!uncertainId || !uncertainKind) return;
    let alive = true;
    void (async () => {
      try {
        const path = uncertainKind === 'configure' ? '/source/configuration/requests/' : '/source/requests/';
        await request('GET', '/' + id + path + uncertainId);
        const current = await request<SkillDetail>('GET', '/' + id);
        if (alive) { changed(current); setFields(current.source?.configuration ?? empty); sessionStorage.removeItem(key); setUncertain(undefined); }
      } catch { /* The explicit Check original request action remains available. */ }
    })();
    return () => { alive = false; };
  }, [id, key, uncertainId, uncertainKind, changed]);
  useEffect(() => {
    const rid = job?.requestId ?? detail.source?.lastRequestId;
    if (!rid) return;
    let alive = true, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await request<SkillSourceJob>('GET', '/' + id + '/source/requests/' + rid);
        if (!alive) return;
        setJob(value);
        if (terminal.has(value.phase)) {
          const current = await request<SkillDetail>('GET', '/' + id);
          if (alive) changed(current);
          return;
        }
        if (value.phase === 'unknown') return;
      } catch (cause) { if (alive) setError((cause as Error).message); }
      if (alive) timer = setTimeout(() => void poll(), 2000);
    };
    void poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [id, job?.requestId, detail.source?.lastRequestId, changed]);
  function remember(intent: Intent) {
    // This stores original IDs and non-secret source fields, never credentials.
    sessionStorage.setItem(key, JSON.stringify(intent)); setUncertain(intent);
  }
  function clear() { sessionStorage.removeItem(key); setUncertain(undefined); }
  async function observe() {
    if (!uncertain || busy) return;
    setBusy(true); setError('');
    try {
      if (uncertain.kind === 'configure') await request('GET', '/' + id + '/source/configuration/requests/' + uncertain.requestId);
      else setJob(await request<SkillSourceJob>('GET', '/' + id + '/source/requests/' + uncertain.requestId));
      const current = await request<SkillDetail>('GET', '/' + id); changed(current); setFields(current.source?.configuration ?? empty);
      clear(); setNotice('The original request was found. Its current state is shown below.');
    } catch (cause) { setError((cause as Error).message + ' The original request is retained. Do not start a replacement while its outcome is unknown.'); }
    finally { setBusy(false); }
  }
  async function checkStatus() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await refreshAuth();
      const rid = job?.requestId ?? detail.source?.lastRequestId;
      if (rid) setJob(await request<SkillSourceJob>('GET', '/' + id + '/source/requests/' + rid));
      changed(await request<SkillDetail>('GET', '/' + id));
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function configure(source: SkillSourceConfiguration | null) {
    if (locked) return;
    const epoch = lifetime.current;
    setBusy(true); setError(''); setNotice('');
    const intent: Intent = { kind: 'configure', requestId: projectRequestId(), revision: detail.skill.revision, source };
    try {
      remember(intent);
      const current = await request<SkillDetail>('PUT', '/' + id + '/source',
        { revision: intent.revision, source, requestId: intent.requestId }, token);
      if (epoch !== lifetime.current) return;
      clear(); changed(current); setFields(current.source?.configuration ?? empty); setJob(undefined);
      setNotice(source ? 'Source saved. Activate explicitly to download and prepare it.' : 'Source disconnected. Published instruction files are preserved; runtime access ends for future runs.');
    } catch (cause) {
      if (epoch !== lifetime.current) return;
      const status = (cause as { status?: number }).status;
      if (status && status >= 400 && status < 500) clear();
      setError((cause as Error).message);
    } finally { if (epoch === lifetime.current) setBusy(false); }
  }
  async function start(action: 'activate' | 'update') {
    if (locked || dirty || !detail.source) return;
    const epoch = lifetime.current;
    setBusy(true); setError(''); setNotice('');
    const intent: Intent = { kind: action, requestId: projectRequestId() };
    try {
      remember(intent);
      const value = await request<SkillSourceJob>('POST', '/' + id + '/source/' + action,
        { revision: detail.skill.revision, sourceRevision: detail.source.revision, draftHash: detail.draftHash, requestId: intent.requestId }, token);
      if (epoch !== lifetime.current) return;
      setJob(value); changed(await request<SkillDetail>('GET', '/' + id)); clear();
    } catch (cause) {
      if (epoch !== lifetime.current) return;
      const status = (cause as { status?: number }).status;
      if (status && status >= 400 && status < 500) clear();
      setError((cause as Error).message);
    } finally { if (epoch === lifetime.current) setBusy(false); }
  }
  function repository(value: string) {
    const rea = /^https:\/\/github\.com\/morluto\/rea(?:\.git)?\/?$/i.test(value.trim());
    setFields(current => ({ ...current, repository: value, recipe: rea ? 'rea' : null,
      skillPath: rea ? '.agents/skills/reverse-engineer-anything' : current.recipe === 'rea' ? '' : current.skillPath }));
  }
  const active = detail.source?.active;
  return <details className="skill-source" open={!!detail.source || !!fields.repository}>
    <summary>GitHub source{active ? ' · active' : detail.source ? ' · configured' : ' · optional'}</summary>
    <div className="skill-source-fields"><label>GitHub repository<input type="url" value={fields.repository} disabled={locked} maxLength={512}
      placeholder="https://github.com/owner/repository" onChange={event => repository(event.target.value)} /></label>
      <label>Ref<input value={fields.ref} disabled={locked} maxLength={240} placeholder="Default branch" onChange={event => setFields(v => ({ ...v, ref: event.target.value }))} /></label>
      <label>Skill path<input value={fields.skillPath} disabled={locked} maxLength={240} placeholder="Repository root" onChange={event => setFields(v => ({ ...v, skillPath: event.target.value }))} /></label>
      <label>GitHub connection<select value={fields.connectionId ?? ''} disabled={locked} onChange={event => setFields(v => ({ ...v, connectionId: event.target.value || null }))}>
        <option value="">Public · no credentials</option>{connections.map(connection => <option key={connection.id} value={connection.id}>{connection.name}</option>)}
        {fields.connectionId && !connections.some(c => c.id === fields.connectionId) && <option value={fields.connectionId}>Saved connection · unavailable</option>}
      </select></label></div>
    {fields.recipe === 'rea' && <p>REA includes a managed analysis runtime. Its actual program capabilities are checked during preparation.</p>}
    <div className="skill-source-actions"><button type="button" disabled={locked || !dirty || !fields.repository} onClick={() => void configure(fields)}>Save source</button>
      <button type="button" disabled={locked || !dirty} onClick={() => setFields(detail.source?.configuration ?? empty)}>Cancel source edits</button>
      {detail.source && <><button type="button" disabled={locked || dirty} onClick={() => void start(active ? 'update' : 'activate')}>{active ? 'Update' : 'Activate'}</button>
        <button type="button" disabled={locked || dirty} onClick={() => void configure(null)}>Disconnect source</button></>}
      {uncertain && <button type="button" disabled={busy} onClick={() => void observe()}>Check original request</button>}
      <button type="button" disabled={busy} onClick={() => void checkStatus()}>Check status / refresh access</button>
    </div>
    <div className="skill-source-status" aria-live="polite">
      {active && <p>Active commit: <code>{active.commit}</code>{active.runtime ? ' · REA ' + active.runtime.version : ''}</p>}
      {runtime && <details><summary>{runtime.ready ? `Ready · ${runtime.tools} native tools` : 'Runtime proof unavailable'}</summary>
        {runtime.reason && <p role="alert">{runtime.reason}</p>}
        {runtime.ready && <>
          <p>Managed Node {runtime.node} · npm {runtime.npm}. Installation probe; target-specific capabilities are checked again by REA during use.</p>
          <ul>{runtime.programs?.map(program => <li key={program.id}>{program.id} {program.version} · <a href={program.origin} target="_blank" rel="noreferrer">Source</a></li>)}</ul>
          <p>{runtime.debianArchives} private system archives. No global package installation.</p>
          {runtime.availability?.groups.map((group, index) => <details key={index}><summary>{group.names.length} tools · {group.available ? 'available before target selection' : group.reason ?? group.availability_code ?? 'require a matching target'}</summary>
            <p>{group.names.join(', ')}</p></details>)}
          <p>Optional requirements: {runtime.externalRequirements?.join('; ')}.</p>
          <p>Use the enabled REA skill in a project session, then discover its native tools. Project files are available at /workspace; results remain in that project or its private session.</p>
        </>}
      </details>}
      {job && <p>Preparation: {job.phase}{job.commit && <> · requested commit: <code>{job.commit}</code></>}</p>}
      {job?.phase === 'complete' && <p>{job.result?.published === true ? job.result?.packageHash === active?.packageHash ? 'The confirmed package is active.' : 'This request completed; the current active package is shown above.' : 'Sources downloaded. The analysis runtime and skill are not active yet.'}</p>}
      {job?.error && <p role="alert">{job.error}{active ? ' The confirmed active revision is still available.' : ''}</p>}
      {job?.phase === 'unknown' && <p role="alert">The original process outcome is unconfirmed. A replacement operation is blocked until it is reconciled.</p>}
      {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
      <p>Saving source settings starts no download. Activate or Update prepares the selected commit. Session skill choices and tool permissions apply from the next run. Existing runs keep their accepted revision.</p>
    </div>
  </details>;
}
