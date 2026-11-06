import { deferView, ViewRecovery } from './DeferredView';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Icon } from './Icon';
import { navigation } from './navigation';
import type { Tab } from './navigation';
import { useProviders } from '../features/llm-providers/useProviders';
import { percent } from '../features/llm-providers/usage-format';
import { useVms } from '../features/virtual-machines/useVms';
import { version } from '../../../shared/version.json';
import type { ComponentKind } from '../../../shared/components';
import type { ProjectNavigation } from '../features/projects/ProjectsWorkspace';
import { editorRegistry } from '../features/project-editor/registry';
import { useConnections } from '../features/github-connections/useConnections';
import { parseRoadmapRoute, roadmapHash } from '../features/project-roadmaps/location';
import { parseBoardRoute, boardHash } from '../features/project-boards/location';
import { useRemoteHosts } from '../features/remote-hosts/useRemoteHosts';
import { parseRemoteHostRoute, remoteHostHash } from '../features/remote-hosts/location';
import { StatusWorkspace } from '../features/status/StatusWorkspace';
import { AiLimitsPanel } from '../features/status/AiLimitsPanel';

const SystemToolsPanel = deferView(() => import('../features/system-tools/SystemToolsPanel').then(module => ({default: module.SystemToolsPanel})));
const StatisticsPanel = deferView(() => import('../features/statistics/StatisticsPanel').then(module => ({default: module.StatisticsPanel})));
const ProviderPanel = deferView(() => import('../features/llm-providers/components/ProviderPanel').then(module => ({default: module.ProviderPanel})));
const VmPanel = deferView(() => import('../features/virtual-machines/VmPanel').then(module => ({default: module.VmPanel})));
const UpdatesPanel = deferView(() => import('../features/updates/UpdatesPanel').then(module => ({default: module.UpdatesPanel})));
const ComponentUpdatesPanel = deferView(() => import('../features/updates/ComponentUpdatesPanel').then(module => ({default: module.ComponentUpdatesPanel})));
const ProjectsWorkspace = deferView(() => import('../features/projects/ProjectsWorkspace').then(module => ({default: module.ProjectsWorkspace})));
const SystemPromptPanel = deferView(() => import('../features/settings/SystemPromptPanel').then(module => ({default: module.SystemPromptPanel})));
const ConnectionPanel = deferView(() => import('../features/github-connections/ConnectionPanel').then(module => ({default: module.ConnectionPanel})));
const HostPanel = deferView(() => import('../features/remote-hosts/HostPanel').then(module => ({default: module.HostPanel})));
const ToolsWorkspace = deferView(() => import('../features/skills/ToolsWorkspace'));
const tabs: Tab[] = ['Status', 'System', 'Projects', 'Tools'];
const statusRoute = ['#status', '#status/ai-limits'].includes(window.location.hash);
const sessionRoute = /^#projects\/([a-f0-9-]{36})\/sessions\/([a-f0-9-]{36})$/.exec(window.location.hash);
const projectStatisticsRoute = /^#projects\/([a-f0-9-]{36})\/statistics$/.exec(window.location.hash);
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
  const [tab, setTab] = useState<Tab>(statusRoute ? 'Status' : sessionRoute || projectRoute || projectStatisticsRoute || roadmapRoute || boardRoute || window.location.hash === '#projects' ? 'Projects' : skillRoute || window.location.hash === '#tools' ? 'Tools' : 'System');
  const [skillId, setSkillId] = useState<string | null>(skillRoute?.[1] ?? null);
  const [skillSessions, setSkillSessions] = useState<Record<string, string | undefined>>(skillRoute ? { [skillRoute[1]]: skillRoute[2] } : {});
  const navigateSkill = useCallback((id: string, session?: string) => setSkillSessions((previous) => ({ ...previous, [id]: session })), []);
  const acceptedHash = useRef(window.location.hash);
  useEffect(() => { acceptedHash.current = window.location.hash; });
  const toolsLeaveGuard = useRef<() => boolean>(() => true);
  const setToolsLeaveGuard = useCallback((guard: () => boolean) => { toolsLeaveGuard.current = guard; }, []);
  const [vmId, setVmId] = useState<string | null>(null);
  const [remoteHostId, setRemoteHostId] = useState<string | null>(remoteHostRoute?.id ?? null);
  const [projectId, setProjectId] = useState<string | null>(sessionRoute?.[1] ?? projectRoute?.[1] ?? projectStatisticsRoute?.[1] ?? roadmapRoute?.projectId ?? boardRoute?.projectId ?? null);
  const [projectNavigation, setProjectNavigation] = useState<Record<string, ProjectNavigation>>(projectStatisticsRoute ? { [projectStatisticsRoute[1]]: { section: 'Statistics', settingsView: 'General' } } : boardRoute
    ? { [boardRoute.projectId]: { section: 'Boards', settingsView: 'General', boardId: boardRoute.boardId } } : roadmapRoute
    ? { [roadmapRoute.projectId]: { section: 'Roadmap', settingsView: 'General', roadmapVersionId: roadmapRoute.versionId } }
    : sessionRoute ? { [sessionRoute[1]]: { section: 'Sessions', settingsView: 'General', sessionId: sessionRoute[2] } } : {});
  const selectProject = useCallback((id: string | null) => {
    setProjectId(id);
    const selected = id ? projectNavigation[id] : undefined;
    window.history.replaceState(null, '', id ? selected?.section === 'Statistics' ? `#projects/${id}/statistics` : selected?.section === 'Boards' ? boardHash(id, selected.boardId) : selected?.section === 'Roadmap' ? roadmapHash(id, selected.roadmapVersionId) : '#projects/' + id : '#projects');
  }, [projectNavigation]);
  const projectLeaveGuard = useRef<() => boolean>(() => true);
  const settingsLeaveGuard = useRef<() => boolean>(() => true);
  const setSettingsLeaveGuard = useCallback((guard: () => boolean) => { settingsLeaveGuard.current = guard; }, []);
  const setProjectLeaveGuard = useCallback((guard: () => boolean) => { projectLeaveGuard.current = guard; }, []);
  const navigateProject = useCallback((id: string, value: ProjectNavigation) => {
    setProjectNavigation((previous) => ({ ...previous, [id]: value }));
    const hash = value.section === 'Statistics' ? `#projects/${id}/statistics` : value.section === 'Boards' ? boardHash(id, value.boardId) : value.section === 'Roadmap' ? roadmapHash(id, value.roadmapVersionId) : value.section === 'Sessions' && value.sessionId ? `#projects/${id}/sessions/${value.sessionId}` : '#projects/' + id;
    if ((value.section === 'Statistics' || /^#projects\/[a-f0-9-]{36}\/statistics$/.test(window.location.hash) || value.section === 'Roadmap' || value.section === 'Boards' || parseRoadmapRoute(window.location.hash) || parseBoardRoute(window.location.hash)) && window.location.hash !== hash) window.history.pushState(null, '', hash);
  }, []);
  const [selected, setSelected] = useState<Selection>({
    group: window.location.hash === '#system/tools' ? 5 : window.location.hash === '#statistics' ? 4 : remoteHostRoute ? 2 : window.location.hash === '#updates' ? 3 : 0, item: window.location.hash === '#system-prompt' ? 1 : window.location.hash === '#skill-manager-prompt' ? 3 : 0, view: remoteHostRoute?.view === 'Settings' ? 1 : 0,
  });
  useEffect(() => {
    const restore = () => {
      const hash = window.location.hash;
      if (hash === acceptedHash.current) return;
      const project = /^#projects\/([a-f0-9-]{36})\/sessions\/([a-f0-9-]{36})$/.exec(hash);
      const projectStatistics = /^#projects\/([a-f0-9-]{36})\/statistics$/.exec(hash);
      const projectEntry = /^#projects\/([a-f0-9-]{36})$/.exec(hash);
      const roadmap = parseRoadmapRoute(hash);
      const board = parseBoardRoute(hash);
      const remoteHost = parseRemoteHostRoute(hash);
      const skill = /^#tools\/skills\/([a-f0-9-]{36})(?:\/sessions\/([a-f0-9-]{36}))?$/.exec(hash);
      if (!project && !projectEntry && !projectStatistics && !roadmap && !board && !remoteHost && !skill && !['', '#status', '#status/ai-limits', '#system', '#tools', '#projects', '#system-prompt', '#skill-manager-prompt', '#updates', '#statistics', '#system/tools'].includes(hash)) return;
      if (!settingsLeaveGuard.current() || !projectLeaveGuard.current() || !toolsLeaveGuard.current()) {
        window.history.replaceState(null, '', acceptedHash.current || window.location.pathname); return;
      }
      acceptedHash.current = hash;
      if (hash === '#status' || hash === '#status/ai-limits') setTab('Status');
      else if (projectStatistics) { setProjectId(projectStatistics[1]); navigateProject(projectStatistics[1], { section: 'Statistics', settingsView: 'General' }); setTab('Projects'); }
      else if (remoteHost) { setRemoteHostId(remoteHost.id); setSelected({ group: 2, item: 0, view: remoteHost.view === 'Settings' ? 1 : 0 }); setTab('System'); }
      else if (board) { setProjectId(board.projectId); navigateProject(board.projectId, { section: 'Boards', settingsView: 'General', boardId: board.boardId }); setTab('Projects'); }
      else if (roadmap) { setProjectId(roadmap.projectId); navigateProject(roadmap.projectId, { section: 'Roadmap', settingsView: 'General', roadmapVersionId: roadmap.versionId }); setTab('Projects'); }
      else if (project) { setProjectId(project[1]); navigateProject(project[1], { section: 'Sessions', settingsView: 'General', sessionId: project[2] }); setTab('Projects'); }
      else if (projectEntry) {
        setProjectId(projectEntry[1]); setTab('Projects');
        setProjectNavigation((previous) => ['Roadmap', 'Boards', 'Statistics'].includes(previous[projectEntry[1]]?.section ?? '')
          ? { ...previous, [projectEntry[1]]: { section: 'Sessions', settingsView: 'General' } } : previous);
      }
      else if (skill) { setSkillId(skill[1]); navigateSkill(skill[1], skill[2]); setTab('Tools'); }
      else if (hash === '#tools') { setSkillId(null); setTab('Tools'); }
      else if (hash === '#projects') setTab('Projects');
      else { setTab('System'); if (hash === '#system-prompt' || hash === '#skill-manager-prompt') setSelected({ group: 0, item: hash === '#system-prompt' ? 1 : 3, view: 0 }); else if (hash === '#updates') setSelected({ group: 3, item: 0, view: 0 }); else if (hash === '#statistics') setSelected({ group: 4, item: 0, view: 0 }); else if (hash === '#system/tools') setSelected({ group: 5, item: 0, view: 0 }); }
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
  const providerPage = tab === 'System' && group.name === 'Settings' && item === 'AI Provider';
  const systemToolsPage = tab === 'System' && group.name === 'Tools';
  const singleColumnPage = tab === 'System' && ['Statistics', 'Tools'].includes(group.name);
  const statisticsPage = tab === 'System' && group.name === 'Statistics';
  const systemPromptPage = tab === 'System' && group.name === 'Settings' && item === 'System Prompt';
  const skillPromptPage = tab === 'System' && group.name === 'Settings' && item === 'Skill Manager Prompt';
  const githubPage = tab === 'System' && group.name === 'Settings' && item === 'GitHub';
  const github = useConnections(githubPage);
  const activeConnection = github.connections.find((connection) => connection.id === connectionView);
  const providers = useProviders(providerPage || tab === 'Status');
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
    const setHash = (hash: string) => {
      if (window.location.hash === hash) return;
      const method = next.group === 5 || window.location.hash === '#system/tools' ? 'pushState' : 'replaceState';
      window.history[method](null, '', hash);
    };
    if (next.group === 5) setHash('#system/tools');
    else if (next.group === 4) setHash('#statistics');
    else if (next.group === 0 && next.item === 1) setHash('#system-prompt');
    else if (next.group === 0 && next.item === 3) setHash('#skill-manager-prompt');
    else if (['#system-prompt', '#skill-manager-prompt', '#statistics', '#system/tools'].includes(window.location.hash) || parseRemoteHostRoute(window.location.hash)) setHash(window.location.pathname);
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
    const projectStats = projectId && projectNavigation[projectId]?.section === 'Statistics' ? `#projects/${projectId}/statistics` : null;
    const board = projectId && projectNavigation[projectId]?.section === 'Boards' ? boardHash(projectId, projectNavigation[projectId].boardId) : null;
    const roadmap = projectId && projectNavigation[projectId]?.section === 'Roadmap' ? roadmapHash(projectId, projectNavigation[projectId].roadmapVersionId) : null;
    window.history.pushState(null, '', value === 'Status' ? '#status/ai-limits' : value === 'Projects' ? (projectStats ?? board ?? roadmap ?? (session ? `#projects/${projectId}/sessions/${session}` : projectId ? '#projects/' + projectId : '#projects')) : value === 'Tools' ? (skillId ? `#tools/skills/${skillId}${skillSessions[skillId] ? '/sessions/' + skillSessions[skillId] : ''}` : '#tools') : selected.group === 5 ? '#system/tools' : selected.group === 4 ? '#statistics' : selected.group === 2 ? remoteHostHash(remoteHostId, selected.view === 1 ? 'Settings' : 'Overview') : selected.group === 0 && selected.item === 1 ? '#system-prompt' : selected.group === 0 && selected.item === 3 ? '#skill-manager-prompt' : '#system');
    setTab(value); return true;
  }

  const reloadView = useCallback(() => {
    if (editorRegistry.hasWorking()) return;
    if (tab === 'System' && !settingsLeaveGuard.current()) return;
    if (tab === 'Projects' && !projectLeaveGuard.current()) return;
    if (tab === 'Tools' && !toolsLeaveGuard.current()) return;
    window.location.reload();
  }, [tab]);

  return (
    <ViewRecovery.Provider value={reloadView}><div className="studio">
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
              <Icon name={name === 'Status' ? 'statistics' : name === 'System' ? 'system' : name === 'Tools' ? 'box' : 'folder'} />{name}
            </button>
          ))}
        </div>
      </header>

      <div className={`workspace ${tab === 'Status' ? 'status-workspace' : singleColumnPage ? 'single-area-workspace' : tab === 'Projects' && projectNavigation[projectId ?? '']?.section === 'Statistics' ? 'statistics-project' : ''}`} role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === 'Status' ? <StatusWorkspace><AiLimitsPanel api={providers} /></StatusWorkspace> : tab === 'Tools' ? <ToolsWorkspace selectedId={skillId} sessionId={skillSessions[skillId ?? '']} navigate={navigateSkill} select={setSkillId} setLeaveGuard={setToolsLeaveGuard} /> : tab === 'Projects' ? <ProjectsWorkspace selectedId={projectId} select={selectProject}
          navigation={projectNavigation} navigate={navigateProject} setLeaveGuard={setProjectLeaveGuard} /> : <>
        <aside className={`navigation ${singleColumnPage ? 'single-area-workspace' : ''}`} aria-label={`${tab} navigation`}>
          <nav className="nav-column" aria-label="Areas">
            <div className="column-heading">Areas</div>
            <div className="nav-items">
              {groups.map((entry, index) => (
                <button type="button" key={entry.name} className={`nav-item ${selected.group === index ? 'selected' : ''}`}
                  aria-current={selected.group === index ? 'true' : undefined}
                  onClick={() => select({ group: index, item: 0, view: 0 })}>
                  <Icon name={entry.icon} /><span>{entry.name}</span>{!['Statistics', 'Tools'].includes(entry.name) && <Icon name="chevron" className="item-chevron" />}
                </button>
              ))}
            </div>
          </nav>
          {!singleColumnPage && <><nav className="nav-column" aria-label="Components">
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
                const account = provider ? providers.nativeProviders.find(p => p.id === provider.id) : undefined;
                const remaining = provider ? providers.remainingByProvider[provider.id] : null;
                const limits = provider ? providers.connectionLimits[provider.id] : null;
                const state = limits?.state ?? (provider ? providers.usageByProvider[provider.id]?.state : undefined);
                const apiLimits = provider?.type === 'api' && ['claude-plan', 'openrouter', 'zai-coding-plan'].includes(provider.kind) && provider.enabled;
                const held = !!limits?.zai?.holds?.length;
                return <button type="button" key={githubPage ? (github.connections[index - 1]?.id ?? 'new-connection') : providerPage ? (provider?.id ?? 'new-provider') : name} className={`nav-item view-item ${selectedView === index ? 'selected' : ''}`}
                  aria-current={selectedView === index ? 'page' : undefined}
                  onClick={() => { if (!settingsLeaveGuard.current()) return; if (githubPage) setConnectionView(github.connections[index - 1]?.id ?? null); else if (providerPage) setProviderView(provider?.id ?? null); else select({ view: index }); }}>
                  {providerPage ? <>
                    {index === 0 && <span className="view-number" aria-hidden="true">+</span>}
                    <span className="provider-view-name">{name}</span>
                    {(account?.status === 'connected' && account.account || apiLimits) &&
                      <span className="provider-remaining" data-state={held ? 'held' : state} title={remaining == null
                        ? `${held ? 'Access held. ' : ''}Remaining usage is not available.` : `${held ? 'Access held. ' : ''}${state === 'stale' ? 'Out of date. ' : ''}${limits?.openrouter ? 'Remaining share of the currently limiting USD spending budget.' : 'Lowest reported remaining usage across quota windows.'}${limits?.checkedAt ? ' Observed '+new Date(limits.checkedAt).toLocaleString()+'.' : ''}`}>
                        {remaining == null ? '—' : percent(remaining)}{state === 'stale' && remaining != null && ' *'}{held && ' !'}
                      </span>}
                  </> : githubPage || vmPage || remotePage || updatePage ? <span className="provider-view-name">{name}</span> : <><span className="view-number">{(index + 1).toString().padStart(2, '0')}</span><span>{name}</span></>}
                </button>;
              })}
            </div>
          </nav></>}
        </aside>

        <main className="main-area">
          <div className="page-heading"><h1>{systemToolsPage ? 'Tools' : statisticsPage ? 'Statistics' : remotePage ? activeRemoteHost?.name ?? (remoteHostId ? 'Remote Host' : 'New Remote Host') : vmPage ? (activeVm?.name ?? 'New virtual machine') : (view ?? item)}</h1><span className="page-rule" /></div>
          {systemToolsPage ? <SystemToolsPanel /> : statisticsPage ? <StatisticsPanel /> : remotePage ? <HostPanel key={`${remoteHostId ?? 'new'}/${view ?? 'Overview'}`} id={remoteHostId} view={view ?? 'Overview'} api={remoteHosts} navigate={navigateRemoteHost} setLeaveGuard={setSettingsLeaveGuard} /> : githubPage ? <ConnectionPanel key={activeConnection?.id ?? 'new-connection'} connection={activeConnection} api={github} select={setConnectionView} setLeaveGuard={setSettingsLeaveGuard} /> : systemPromptPage || skillPromptPage ? <SystemPromptPanel key={skillPromptPage ? 'skill-manager-prompt' : 'system-prompt'} kind={skillPromptPage ? 'skill-manager-prompt' : 'system-prompt'} setLeaveGuard={setSettingsLeaveGuard} /> : updatePage ? componentKind ? <ComponentUpdatesPanel key={componentKind} kind={componentKind} /> : <UpdatesPanel /> : vmPage ? <VmPanel key={activeVm?.id ?? 'new-vm'} api={vms} vm={activeVm} view={view ?? 'Overview'} select={(id) => { setVmId(id); select({ view: 0 }); }} /> : providerPage ? <ProviderPanel provider={activeProvider} api={providers} select={setProviderView} setLeaveGuard={setSettingsLeaveGuard} /> : null}
        </main>
        </>}
      </div>

      <footer className="statusbar">
        <span className="statusbar-name">R4OS Studio</span>
        <span className="statusbar-version">Version {version}</span>
      </footer>
    </div></ViewRecovery.Provider>
  );
}
