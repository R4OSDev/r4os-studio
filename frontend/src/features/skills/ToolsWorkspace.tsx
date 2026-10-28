import { DeleteSkillDialog, pendingSkillDeletion } from './DeleteSkillDialog';
import { projectRequestId } from '../projects/api';
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../../app/Icon';
import { EditorDialog } from '../project-editor/EditorDialog';
import { useSkills } from './useSkills';
import type { FormEvent } from 'react';
import '../project-editor/styles.css';
import './styles.css';
import '../agent-sessions/styles.css';
import '../projects/styles.css';
import { SessionScope, busyRun } from '../agent-sessions/api';
import { useSessions } from '../agent-sessions/useSessions';
import { NewSessionDialog } from '../agent-sessions/NewSessionDialog';
import { SessionPanel } from '../agent-sessions/SessionPanel';
const SkillEditor = lazy(() => import('./SkillEditor'));

type Props = { selectedId: string | null; sessionId?: string; select: (id: string | null) => void; navigate: (id: string, sessionId?: string) => void; setLeaveGuard: (guard: () => boolean) => void };
export default function ToolsWorkspace(props: Props) { return <SessionScope.Provider value="skill"><SkillWorkspace {...props} /></SessionScope.Provider>; }
function SkillWorkspace({ selectedId, sessionId, select, navigate, setLeaveGuard }: Props) {
  const [deletionId,setDeletionId]=useState<string|null>(()=>pendingSkillDeletion(selectedId));
  const selectedRef=useRef(selectedId);useEffect(()=>{selectedRef.current=selectedId;},[selectedId]);
  const api = useSkills(), active = api.skills.find((s) => s.id === selectedId);
  const sessions = useSessions(active?.id ?? null);
  const [newSession, setNewSession] = useState(false), [sessionDirty, setSessionDirty] = useState(false), [sessionBusy, setSessionBusy] = useState(false);
  const { reload: reloadSessions } = sessions, { reload: reloadSkills, forget: forgetSkill } = api;
  const changed = useCallback(() => { reloadSessions(); void reloadSkills(); }, [reloadSessions, reloadSkills]);
  const childGuard = useRef<() => boolean>(() => true);
  const setChildGuard = useCallback((guard: () => boolean) => { childGuard.current = guard; }, []);
  const [creating, setCreating] = useState(false), [name, setName] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const requestId = useRef(projectRequestId());
  const leave = useCallback(() => !busy && !sessionBusy && (!sessionDirty || window.confirm('Discard unsaved session settings?')) && (!creating || !name || window.confirm('Discard the new skill name?')) && childGuard.current(), [busy, creating, name, sessionDirty, sessionBusy]);
  useEffect(() => { setLeaveGuard(leave); return () => setLeaveGuard(() => true); }, [leave, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (busy || sessionBusy || sessionDirty || (creating && name)) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [busy, creating, name, sessionDirty, sessionBusy]);
  function choose(id: string) {
    if (id === selectedId || !leave()) return;
    select(id); window.history.pushState(null, '', '#tools/skills/' + id); navigate(id);
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (busy || !name.trim()) return;
    setBusy(true); setError('');
    try {
      const value = await api.create(requestId.current, name); setCreating(false); setName(''); select(value.skill.id);
      navigate(value.skill.id); window.history.pushState(null, '', '#tools/skills/' + value.skill.id);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  function chooseSession(id?: string) { if (!active || !leave()) return; navigate(active.id, id); window.history.pushState(null, '', '#tools/skills/' + active.id + (id ? '/sessions/' + id : '')); }
  function closeNew() { if (!busy && (!name || window.confirm('Discard the new skill name?'))) setCreating(false); }
  const closeDeletion=useCallback(()=>setDeletionId(null),[]);
  const finishDeletion=useCallback(async(id:string)=>{forgetSkill(id);await reloadSkills();if(selectedRef.current===id){setChildGuard(()=>true);setSessionDirty(false);select(null);navigate(id);window.history.replaceState(null,'','#tools');}},[forgetSkill,reloadSkills,select,navigate,setChildGuard]);
  return <>
    <aside className="navigation" aria-label="Tools navigation">
      <nav className="nav-column" aria-label="Tools"><div className="column-heading">TOOLS</div>
        <div className="nav-items"><button type="button" className="nav-item selected" aria-current="true"><Icon name="book" /><span>Skill Manager</span></button></div>
      </nav>
      <nav className="nav-column" aria-label="Skills"><div className="column-heading">SKILLS</div>
        <div className="nav-items"><button type="button" className="nav-item" disabled={!api.token || busy} onClick={() => {
          if (leave()) { requestId.current = projectRequestId(); setName(''); setError(''); setCreating(true); }
        }}><span>+ New Skill</span></button>
          {api.error ? <><p className="skill-nav-message" role="alert">{api.error}</p><button className="nav-item" onClick={() => void api.reload()}>Retry</button></>
            : !api.token ? <p className="skill-nav-message" role="status">Loading skills…</p>
              : api.skills.length === 0 ? <p className="skill-nav-message">No skills yet.</p>
                : api.skills.map((skill) => <button key={skill.id} type="button" className={`nav-item ${active?.id === skill.id ? 'selected' : ''}`} aria-current={active?.id === skill.id ? 'true' : undefined} onClick={() => choose(skill.id)}>
                  <span className="provider-view-name">{skill.name}</span>{!skill.activeRevision && <span className="skill-draft">Draft</span>}
                </button>)}
        </div>
      </nav>
      {active ? <nav className="nav-column" aria-label="Skill views"><div className="column-heading">Views</div>
        <div className="nav-items skill-fixed-views"><button type="button" className="nav-item" disabled={!api.token || busy || sessionBusy} onClick={() => { if (leave()) setNewSession(true); }}>+ Session</button>
          <button type="button" className={`nav-item ${!sessionId ? 'selected' : ''}`} aria-current={!sessionId ? 'page' : undefined} onClick={() => { if (sessionId) chooseSession(); }}>View Skill</button></div>
        <div className="nav-items skill-session-list">{sessions.error ? <><p className="skill-nav-message" role="alert">{sessions.error}</p><button className="nav-item" onClick={sessions.reload}>Retry</button></> : sessions.loading ? <p className="skill-nav-message" role="status">Loading sessions…</p> : sessions.sessions.map((session) => <button key={session.id} type="button" className={`nav-item ${session.id === sessionId ? 'selected' : ''}`} aria-current={session.id === sessionId ? 'page' : undefined} onClick={() => { if (session.id !== sessionId) chooseSession(session.id); }}><span className="provider-view-name">{session.name}</span>{busyRun(session.latestRun?.state) && <span className="session-nav-status" aria-label="Run active" />}</button>)}</div>
      </nav> : <div className="nav-column" aria-hidden="true" />}
    </aside>
    <main className="main-area skill-main" aria-label="Tools content" tabIndex={-1}>
      {active && sessionId ? sessions.loading ? <p className="skill-empty">Loading session…</p> : sessions.sessions.some((session) => session.id === sessionId) ? <SessionPanel key={'skill:' + active.id + ':' + sessionId} projectId={active.id} sessionId={sessionId} token={api.token} changed={changed} refreshAuth={api.reload} dirtyChanged={setSessionDirty} busyChanged={setSessionBusy} /> : <p className="skill-empty">The selected session is unavailable. Select a session or View Skill.</p> : active ? <Suspense fallback={<p className="skill-empty">Loading skill…</p>}><SkillEditor key={active.id} id={active.id} token={api.token}
        deleteSkill={()=>setDeletionId(active.id)} remembered={api.remember} setLeaveGuard={setChildGuard} refreshAuth={api.reload} /></Suspense>
        : <p className="skill-empty">{selectedId && api.token ? 'The selected skill is unavailable. Select another skill or create one.' : 'Select a skill or create one.'}</p>}
    </main>
    {deletionId && <DeleteSkillDialog key={deletionId} id={deletionId} token={api.token} reauth={api.reload} close={closeDeletion} deleted={finishDeletion} />}
    {newSession && active && <NewSessionDialog key={active.id} projectId={active.id} token={api.token} close={() => setNewSession(false)} dirtyChanged={setSessionDirty} busyChanged={setSessionBusy} created={(session) => { setNewSession(false); setSessionDirty(false); sessions.reload(); navigate(active.id, session.id); window.history.pushState(null, '', '#tools/skills/' + active.id + '/sessions/' + session.id); }} />}
    {creating && <EditorDialog label="New skill" busy={busy} close={closeNew}>
      <form onSubmit={(event) => void create(event)}><h2>New skill</h2><label htmlFor="new-skill-name">Skill name</label>
        <input id="new-skill-name" value={name} maxLength={120} required disabled={busy} onChange={(event) => setName(event.target.value)} />
        {error && <p role="alert">{error}</p>}
        <div className="editor-dialog-actions"><button type="button" disabled={busy} onClick={closeNew}>Cancel</button>
          <button type="submit" disabled={busy || !name.trim()}>{busy ? 'Creating…' : 'Create skill'}</button></div>
      </form>
    </EditorDialog>}
  </>;
}
