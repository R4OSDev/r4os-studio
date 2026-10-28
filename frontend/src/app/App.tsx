import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Icon } from './Icon';
import { navigation } from './navigation';
import type { Tab } from './navigation';
import { useProviders } from '../features/llm-providers/useProviders';
import { ProviderPanel } from '../features/llm-providers/components/ProviderPanel';
import { percent } from '../features/llm-providers/usage-format';
import { useVms } from '../features/virtual-machines/useVms';
import { VmPanel } from '../features/virtual-machines/VmPanel';
import { version } from '../../../shared/version.json';
import { UpdatesPanel } from '../features/updates/UpdatesPanel';
import { ComponentUpdatesPanel } from '../features/updates/ComponentUpdatesPanel';
import type { ComponentKind } from '../../../shared/components';
import { ProjectsWorkspace } from '../features/projects/ProjectsWorkspace';
import type { ProjectNavigation } from '../features/projects/ProjectsWorkspace';
import { SystemPromptPanel } from '../features/settings/SystemPromptPanel';
import { editorRegistry } from '../features/project-editor/registry';
import { useConnections } from '../features/github-connections/useConnections';
import { ConnectionPanel } from '../features/github-connections/ConnectionPanel';
import { parseRoadmapRoute, roadmapHash } from '../features/project-roadmaps/location';
import { parseBoardRoute, boardHash } from '../features/project-boards/location';
import { useRemoteHosts } from '../features/remote-hosts/useRemoteHosts';
import { HostPanel } from '../features/remote-hosts/HostPanel';
import { parseRemoteHostRoute, remoteHostHash } from '../features/remote-hosts/location';

const ToolsWorkspace = lazy(() => import('../features/skills/ToolsWorkspace'));
const tabs: Tab[] = ['System', 'Projects', 'Tools'];
const sessionRoute = /^#projects\/([a-f0-9-]{36})\/sessions\/([a-f0-9-]{36})$/.exec(window.location.hash);
const projectRoute = /^#projects\/([a-f0-9-]{36})$/.exec(window.location.hash);
const roadmapRoute = parseRoadmapRoute(window.location.hash);
const boardRoute = parseBoardRoute(window.location.hash);
const remoteHostRoute = parseRemoteHostRoute(window.location.hash);
const skillRoute = /^#tools\/skills\/([a-f0-9-]{36})(?:\/sessions\/([a-f0-9-]{36}))?$/.exec(window.location.hash);
type Selection = { group: number; item: number; view: number };

export function App() {
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (editorRegistry.hasUnsaved() || editorRegistry.hasWorking()) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, []);
  const [tab, setTab] = useState<Tab>(sessionRoute || projectRoute || roadmapRoute || boardRoute || window.location.hash === '#projects' ? 'Projects' : skillRoute || window.location.hash === '#tools' ? 'Tools' : 'System');
  const [skillId, setSkillId] = useState<string | null>(skillRoute?.[1] ?? null);
  const [skillSessions, setSkillSessions] = useState<Record<string, string | undefined>>(skillRoute ? { [skillRoute[1]]: skillRoute[2] } : {});
  const navigateSkill = useCallback((id: string, session?: string) => setSkillSessions((previous) => ({ ...previous, [id]: session })), []);
  const acceptedHash = useRef(window.location.hash);
  useEffect(() => { acceptedHash.current = window.location.hash; });
  const toolsLeaveGuard = useRef<() => boolean>(() => true);
  const setToolsLeaveGuard = useCallback((guard: () => boolean) => { toolsLeaveGuard.current = guard; }, []);
  const [vmId, setVmId] = useState<string | null>(null);
  const [remoteHostId, setRemoteHostId] = useState<string | null>(remoteHostRoute?.id ?? null);
  const [projectId, setProjectId] = useState<string | null>(sessionRoute?.[1] ?? projectRoute?.[1] ?? roadmapRoute?.projectId ?? boardRoute?.projectId ?? null);
  const [projectNavigation, setProjectNavigation] = useState<Record<string, ProjectNavigation>>(boardRoute
    ? { [boardRoute.projectId]: { section: 'Boards', settingsView: 'General', boardId: boardRoute.boardId } } : roadmapRoute
    ? { [roadmapRoute.projectId]: { section: 'Roadmap', settingsView: 'General', roadmapVersionId: roadmapRoute.versionId } }
    : sessionRoute ? { [sessionRoute[1]]: { section: 'Sessions', settingsView: 'General', sessionId: sessionRoute[2] } } : {});
  const selectProject = useCallback((id: string | null) => {
    setProjectId(id);
    const selected = id ? projectNavigation[id] : undefined;
    window.history.replaceState(null, '', id ? selected?.section === 'Boards' ? boardHash(id, selected.boardId) : selected?.section === 'Roadmap' ? roadmapHash(id, selected.roadmapVersionId) : '#projects/' + id : '#projects');
  }, [projectNavigation]);
  const projectLeaveGuard = useRef<() => boolean>(() => true);
  const settingsLeaveGuard = useRef<() => boolean>(() => true);
  const setSettingsLeaveGuard = useCallback((guard: () => boolean) => { settingsLeaveGuard.current = guard; }, []);
  const setProjectLeaveGuard = useCallback((guard: () => boolean) => { projectLeaveGuard.current = guard; }, []);
  const navigateProject = useCallback((id: string, value: ProjectNavigation) => {
    setProjectNavigation((previous) => ({ ...previous, [id]: value }));
    const hash = value.section === 'Boards' ? boardHash(id, value.boardId) : value.section === 'Roadmap' ? roadmapHash(id, value.roadmapVersionId) : value.section === 'Sessions' && value.sessionId ? `#projects/${id}/sessions/${value.sessionId}` : '#projects/' + id;
    if ((value.section === 'Roadmap' || value.section === 'Boards' || parseRoadmapRoute(window.location.hash) || parseBoardRoute(window.location.hash)) && window.location.hash !== hash) window.history.pushState(null, '', hash);
  }, []);
  const [selected, setSelected] = useState<Selection>({
    group: remoteHostRoute ? 2 : window.location.hash === '#updates' ? 3 : 0, item: window.location.hash === '#system-prompt' ? 1 : window.location.hash === '#skill-manager-prompt' ? 3 : 0, view: remoteHostRoute?.view === 'Settings' ? 1 : 0,
  });
  useEffect(() => {
    const restore = () => {
      const hash = window.location.hash;
      if (hash === acceptedHash.current) return;
      const project = /^#projects\/([a-f0-9-]{36})\/sessions\/([a-f0-9-]{36})$/.exec(hash);
      const projectEntry = /^#projects\/([a-f0-9-]{36})$/.exec(hash);
      const roadmap = parseRoadmapRoute(hash);
      const board = parseBoardRoute(hash);
      const remoteHost = parseRemoteHostRoute(hash);
      const skill = /^#tools\/skills\/([a-f0-9-]{36})(?:\/sessions\/([a-f0-9-]{36}))?$/.exec(hash);
      if (!project && !projectEntry && !roadmap && !board && !remoteHost && !skill && !['', '#system', '#tools', '#projects', '#system-prompt', '#skill-manager-prompt', '#updates'].includes(hash)) return;
      if (!settingsLeaveGuard.current() || !projectLeaveGuard.current() || !toolsLeaveGuard.current()) {
        window.history.replaceState(null, '', acceptedHash.current || window.location.pathname); return;
      }
      acceptedHash.current = hash;
      if (remoteHost) { setRemoteHostId(remoteHost.id); setSelected({ group: 2, item: 0, view: remoteHost.view === 'Settings' ? 1 : 0 }); setTab('System'); }
      else if (board) { setProjectId(board.projectId); navigateProject(board.projectId, { section: 'Boards', settingsView: 'General', boardId: board.boardId }); setTab('Projects'); }
      else if (roadmap) { setProjectId(roadmap.projectId); navigateProject(roadmap.projectId, { section: 'Roadmap', settingsView: 'General', roadmapVersionId: roadmap.versionId }); setTab('Projects'); }
      else if (project) { setProjectId(project[1]); navigateProject(project[1], { section: 'Sessions', settingsView: 'General', sessionId: project[2] }); setTab('Projects'); }
      else if (projectEntry) {
        setProjectId(projectEntry[1]); setTab('Projects');
        setProjectNavigation((previous) => ['Roadmap', 'Boards'].includes(previous[projectEntry[1]]?.section ?? '')
          ? { ...previous, [projectEntry[1]]: { section: 'Sessions', settingsView: 'General' } } : previous);
      }
      else if (skill) { setSkillId(skill[1]); navigateSkill(skill[1], skill[2]); setTab('Tools'); }
      else if (hash === '#tools') { setSkillId(null); setTab('Tools'); }
      else if (hash === '#projects') setTab('Projects');
      else { setTab('System'); if (hash === '#system-prompt' || hash === '#skill-manager-prompt') setSelected({ group: 0, item: hash === '#system-prompt' ? 1 : 3, view: 0 }); else if (hash === '#updates') setSelected({ group: 3, item: 0, view: 0 }); }
    };
    window.addEventListener('hashchange', restore);
    window.addEventListener('popstate', restore);
    return () => { window.removeEventListener('hashchange', restore); window.removeEventListener('popstate', restore); };
  }, [navigateProject, navigateSkill]);
  const [providerView, setProviderView] = useState<string | null>(null);
  const [connectionView, setConnectionView] = useState<string | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const groups = navigation;
  const group = groups[selected.group];
  const vmPage = tab === 'System' && group.name === 'Virtual Machines';
  const updatePage = tab === 'System' && group.name === 'Updates';
  const remotePage = tab === 'System' && group.name === 'Remote Hosts';
  const remoteHosts = useRemoteHosts(remotePage);
  const activeRemoteHost = remoteHosts.hosts.find((host) => host.id === remoteHostId);
  const vms = useVms(vmPage);
  const activeVm = vms.vms.find((vm) => vm.id === vmId);
  const componentItems = remotePage ? ['+ New Host', ...remoteHosts.hosts.map((host) => host.name)] : vmPage ? ['+ New VM', ...vms.vms.map((vm) => vm.name)] : group.items;
  const selectedComponent = remotePage ? (activeRemoteHost ? remoteHosts.hosts.indexOf(activeRemoteHost) + 1 : 0) : vmPage ? (activeVm ? vms.vms.indexOf(activeVm) + 1 : 0) : selected.item;
  const item = componentItems[selectedComponent];
  const providerPage = tab === 'System' && group.name === 'Settings' && item === 'LLM Provider';
  const systemPromptPage = tab === 'System' && group.name === 'Settings' && item === 'System Prompt';
  const skillPromptPage = tab === 'System' && group.name === 'Settings' && item === 'Skill Manager Prompt';
  const githubPage = tab === 'System' && group.name === 'Settings' && item === 'GitHub';
  const github = useConnections(githubPage);
  const activeConnection = github.connections.find((connection) => connection.id === connectionView);
  const providers = useProviders(providerPage);
  const activeProvider = providers.providers.find((provider) => provider.id === providerView);
  const availableViews = remotePage ? (remoteHostId ? ['Overview', 'Settings'] : []) : githubPage ? ['+ Connection', ...github.connections.map((connection) => connection.name)] : vmPage ? (activeVm ? ['Overview', 'Console', 'Settings', 'Exchange', 'Logs'] : []) : providerPage ? ['New Provider', ...providers.providers.map((provider) => provider.name)] : updatePage ? (item === 'Components' ? ['SDK'] : item === 'Tools' ? ['Zig', 'C', 'Rust', 'QEMU', 'Codex', 'R4UPack'] : []) : [];
  const selectedView = githubPage ? (activeConnection ? github.connections.indexOf(activeConnection) + 1 : 0) : providerPage ? (activeProvider ? providers.providers.indexOf(activeProvider) + 1 : 0) : updatePage && item === 'Components' ? 0 : selected.view;
  const view = availableViews[selectedView];
  const componentKind: ComponentKind | 'c' | undefined = updatePage && item !== 'R4OS Studio'
    ? ({ SDK: 'sdk', Contract: 'contract', Libraries: 'libraries', Zig: 'zig', C: 'c', Rust: 'rust', QEMU: 'qemu', Codex: 'codex', R4UPack: 'r4upack', 'R4OS Releases': 'r4os' } as Record<string, ComponentKind | 'c'>)[view ?? item] : undefined;

  function navigateRemoteHost(id: string | null, nextView = 'Overview') {
    setRemoteHostId(id); setSelected({ group: 2, item: 0, view: id && nextView === 'Settings' ? 1 : 0 });
    const hash = remoteHostHash(id, nextView);
    if (window.location.hash !== hash) window.history.pushState(null, '', hash);
  }

  function select(patch: Partial<Selection>) {
    if (!settingsLeaveGuard.current()) return;
    const next = { ...selected, ...patch };
    if (next.group === 2) { navigateRemoteHost(remoteHostId, next.view === 1 ? 'Settings' : 'Overview'); return; }
    if (next.group === 0 && next.item === 1) window.history.replaceState(null, '', '#system-prompt');
    else if (next.group === 0 && next.item === 3) window.history.replaceState(null, '', '#skill-manager-prompt');
    else if (['#system-prompt', '#skill-manager-prompt'].includes(window.location.hash) || parseRemoteHostRoute(window.location.hash)) window.history.replaceState(null, '', window.location.pathname);
    setSelected((previous) => ({ ...previous, ...patch }));
  }

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    switch (event.key) {
      case 'ArrowRight': next = (index + 1) % tabs.length; break;
      case 'ArrowLeft': next = (index + tabs.length - 1) % tabs.length; break;
      case 'Home': next = 0; break;
      case 'End': next = tabs.length - 1; break;
      default: return;
    }
    event.preventDefault();
    if (!switchTab(tabs[next])) return;
    tabRefs.current[next]?.focus();
  }
  function switchTab(value: Tab) {
    if (tab === 'System' && value !== tab && !settingsLeaveGuard.current()) return false;
    if (tab === 'Projects' && value !== tab && !projectLeaveGuard.current()) return false;
    if (tab === 'Tools' && value !== tab && !toolsLeaveGuard.current()) return false;
    if (value === tab) return true;
    const session = projectId ? projectNavigation[projectId]?.sessionId : undefined;
    const board = projectId && projectNavigation[projectId]?.section === 'Boards' ? boardHash(projectId, projectNavigation[projectId].boardId) : null;
    const roadmap = projectId && projectNavigation[projectId]?.section === 'Roadmap' ? roadmapHash(projectId, projectNavigation[projectId].roadmapVersionId) : null;
    window.history.pushState(null, '', value === 'Projects' ? (board ?? roadmap ?? (session ? `#projects/${projectId}/sessions/${session}` : projectId ? '#projects/' + projectId : '#projects')) : value === 'Tools' ? (skillId ? `#tools/skills/${skillId}${skillSessions[skillId] ? '/sessions/' + skillSessions[skillId] : ''}` : '#tools') : selected.group === 2 ? remoteHostHash(remoteHostId, selected.view === 1 ? 'Settings' : 'Overview') : selected.group === 0 && selected.item === 1 ? '#system-prompt' : selected.group === 0 && selected.item === 3 ? '#skill-manager-prompt' : '#system');
    setTab(value); return true;
  }

  return (
    <div className="studio">
      <header className="topbar">
        <a className="brand" href="/" aria-label="R4OS Studio home">
          <span className="brand-mark"><Icon name="terminal" /></span>
          <span>R4OS <span className="brand-light">Studio</span></span>
        </a>
        <div className="tabs" role="tablist" aria-label="Workspaces">
          {tabs.map((name, index) => (
            <button key={name} ref={(element) => { tabRefs.current[index] = element; }}
              id={`tab-${name}`} className={`tab ${tab === name ? 'active' : ''}`}
              type="button" role="tab" aria-selected={tab === name}
              aria-controls={`panel-${name}`} tabIndex={tab === name ? 0 : -1}
              onClick={() => switchTab(name)} onKeyDown={(event) => handleTabKey(event, index)}>
              <Icon name={name === 'System' ? 'system' : name === 'Tools' ? 'box' : 'folder'} />{name}
            </button>
          ))}
        </div>
      </header>

      <div className="workspace" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === 'Tools' ? <Suspense fallback={<p className="skill-empty">Loading tools…</p>}><ToolsWorkspace selectedId={skillId} sessionId={skillSessions[skillId ?? '']} navigate={navigateSkill} select={setSkillId} setLeaveGuard={setToolsLeaveGuard} /></Suspense> : tab === 'Projects' ? <ProjectsWorkspace selectedId={projectId} select={selectProject}
          navigation={projectNavigation} navigate={navigateProject} setLeaveGuard={setProjectLeaveGuard} /> : <>
        <aside className="navigation" aria-label={`${tab} navigation`}>
          <nav className="nav-column" aria-label="Areas">
            <div className="column-heading">Areas</div>
            <div className="nav-items">
              {groups.map((entry, index) => (
                <button type="button" key={entry.name} className={`nav-item ${selected.group === index ? 'selected' : ''}`}
                  aria-current={selected.group === index ? 'true' : undefined}
                  onClick={() => select({ group: index, item: 0, view: 0 })}>
                  <Icon name={entry.icon} /><span>{entry.name}</span><Icon name="chevron" className="item-chevron" />
                </button>
              ))}
            </div>
          </nav>
          <nav className="nav-column" aria-label="Components">
            <div className="column-heading">Components</div>
            <div className="nav-items">
              {componentItems.map((name, index) => (
                <button type="button" key={remotePage && index > 0 ? remoteHosts.hosts[index - 1].id : vmPage && index > 0 ? vms.vms[index - 1].id : name} className={`nav-item ${selectedComponent === index ? 'selected' : ''}`}
                  aria-current={selectedComponent === index ? 'true' : undefined}
                  onClick={() => { if (remotePage) { if (settingsLeaveGuard.current()) navigateRemoteHost(remoteHosts.hosts[index - 1]?.id ?? null); return; } if (vmPage) setVmId(index ? vms.vms[index - 1].id : null); select({ item: index, view: 0 }); }}>
                  <span className="provider-view-name">{name}</span>{vmPage && index > 0 && <span className={`vm-nav-status ${vms.vms[index - 1].state}`} title={vms.vms[index - 1].state} />}{availableViews.length > 0 && <Icon name="chevron" className="item-chevron" />}
                </button>
              ))}
            </div>
          </nav>
          <nav className="nav-column" aria-label="Views">
            <div className="column-heading">Views</div>
            <div className="nav-items">
              {availableViews.map((name, index) => {
                const provider = providerPage && index > 0 ? providers.providers[index - 1] : undefined;
                const remaining = provider ? providers.remainingByProvider[provider.id] : null;
                return <button type="button" key={githubPage ? (github.connections[index - 1]?.id ?? 'new-connection') : providerPage ? (provider?.id ?? 'new-provider') : name} className={`nav-item view-item ${selectedView === index ? 'selected' : ''}`}
                  aria-current={selectedView === index ? 'page' : undefined}
                  onClick={() => { if (!settingsLeaveGuard.current()) return; if (githubPage) setConnectionView(github.connections[index - 1]?.id ?? null); else if (providerPage) setProviderView(provider?.id ?? null); else select({ view: index }); }}>
                  {providerPage ? <>
                    {index === 0 && <span className="view-number" aria-hidden="true">+</span>}
                    <span className="provider-view-name">{name}</span>
                    {provider?.type === 'openai' && provider.status === 'connected' && provider.account &&
                      <span className="provider-remaining" title={remaining == null
                        ? 'Remaining usage is not available.' : 'Lowest reported remaining usage across quota windows.'}>
                        {remaining == null ? '—' : percent(remaining)}
                      </span>}
                  </> : githubPage || vmPage || remotePage || updatePage ? <span className="provider-view-name">{name}</span> : <><span className="view-number">{(index + 1).toString().padStart(2, '0')}</span><span>{name}</span></>}
                </button>;
              })}
            </div>
          </nav>
        </aside>

        <main className="main-area">
          <div className="page-heading"><h1>{remotePage ? activeRemoteHost?.name ?? (remoteHostId ? 'Remote Host' : 'New Remote Host') : vmPage ? (activeVm?.name ?? 'New virtual machine') : (view ?? item)}</h1><span className="page-rule" /></div>
          {remotePage ? <HostPanel key={`${remoteHostId ?? 'new'}/${view ?? 'Overview'}`} id={remoteHostId} view={view ?? 'Overview'} api={remoteHosts} navigate={navigateRemoteHost} setLeaveGuard={setSettingsLeaveGuard} /> : githubPage ? <ConnectionPanel key={activeConnection?.id ?? 'new-connection'} connection={activeConnection} api={github} select={setConnectionView} setLeaveGuard={setSettingsLeaveGuard} /> : systemPromptPage || skillPromptPage ? <SystemPromptPanel key={skillPromptPage ? 'skill-manager-prompt' : 'system-prompt'} kind={skillPromptPage ? 'skill-manager-prompt' : 'system-prompt'} setLeaveGuard={setSettingsLeaveGuard} /> : updatePage ? componentKind ? <ComponentUpdatesPanel key={componentKind} kind={componentKind} /> : <UpdatesPanel /> : vmPage ? <VmPanel key={activeVm?.id ?? 'new-vm'} api={vms} vm={activeVm} view={view ?? 'Overview'} select={(id) => { setVmId(id); select({ view: 0 }); }} /> : providerPage ? <ProviderPanel provider={activeProvider} api={providers} select={setProviderView} /> : null}
        </main>
        </>}
      </div>

      <footer className="statusbar">
        <span className="statusbar-name">R4OS Studio</span>
        <span className="statusbar-version">Version {version}</span>
      </footer>
    </div>
  );
}
