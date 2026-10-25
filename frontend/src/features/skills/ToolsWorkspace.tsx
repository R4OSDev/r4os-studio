import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../../app/Icon';
import { EditorDialog } from '../project-editor/EditorDialog';
import { useSkills } from './useSkills';
import type { FormEvent } from 'react';
import '../project-editor/styles.css';
import './styles.css';
const SkillEditor = lazy(() => import('./SkillEditor'));

export default function ToolsWorkspace({ selectedId, select, setLeaveGuard }: {
  selectedId: string | null; select: (id: string | null) => void; setLeaveGuard: (guard: () => boolean) => void;
}) {
  const api = useSkills(), active = api.skills.find((s) => s.id === selectedId);
  const childGuard = useRef<() => boolean>(() => true);
  const setChildGuard = useCallback((guard: () => boolean) => { childGuard.current = guard; }, []);
  const [creating, setCreating] = useState(false), [name, setName] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const requestId = useRef(crypto.randomUUID());
  const leave = useCallback(() => !busy && (!creating || !name || window.confirm('Discard the new skill name?')) && childGuard.current(), [busy, creating, name]);
  useEffect(() => { setLeaveGuard(leave); return () => setLeaveGuard(() => true); }, [leave, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (busy || (creating && name)) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [busy, creating, name]);
  function choose(id: string) {
    if (id === selectedId || !leave()) return;
    select(id); window.history.replaceState(null, '', '#tools/skills/' + id);
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (busy || !name.trim()) return;
    setBusy(true); setError('');
    try {
      const value = await api.create(requestId.current, name); setCreating(false); setName(''); select(value.skill.id);
      window.history.replaceState(null, '', '#tools/skills/' + value.skill.id);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  function closeNew() { if (!busy && (!name || window.confirm('Discard the new skill name?'))) setCreating(false); }
  return <>
    <aside className="navigation" aria-label="Tools navigation">
      <nav className="nav-column" aria-label="Tools"><div className="column-heading">TOOLS</div>
        <div className="nav-items"><button type="button" className="nav-item selected" aria-current="true"><Icon name="book" /><span>Skill Manager</span></button></div>
      </nav>
      <nav className="nav-column" aria-label="Skills"><div className="column-heading">SKILLS</div>
        <div className="nav-items"><button type="button" className="nav-item" disabled={!api.token || busy} onClick={() => {
          if (leave()) { requestId.current = crypto.randomUUID(); setName(''); setError(''); setCreating(true); }
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
        <div className="nav-items skill-fixed-views"><button type="button" className="nav-item" disabled title="Sessions are not available yet.">+ Session</button>
          <button type="button" className="nav-item selected" aria-current="page">View Skill</button></div>
      </nav> : <div className="nav-column" aria-hidden="true" />}
    </aside>
    <main className="main-area skill-main" aria-label="Tools content">
      {active ? <Suspense fallback={<p className="skill-empty">Loading skill…</p>}><SkillEditor key={active.id} id={active.id} token={api.token}
        remembered={api.remember} setLeaveGuard={setChildGuard} refreshAuth={api.reload} /></Suspense>
        : <p className="skill-empty">{selectedId && api.token ? 'The selected skill is unavailable. Select another skill or create one.' : 'Select a skill or create one.'}</p>}
    </main>
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
