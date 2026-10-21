import { useCallback, useRef, useState } from 'react';
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

const tabs: Tab[] = ['System', 'Projects'];
const sessionRoute = /^#projects\/([a-f0-9-]{36})\/sessions\/([a-f0-9-]{36})$/.exec(window.location.hash);
type Selection = { group: number; item: number; view: number };

export function App() {
  const [tab, setTab] = useState<Tab>(sessionRoute ? 'Projects' : 'System');
  const [vmId, setVmId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(sessionRoute?.[1] ?? null);
  const [projectNavigation, setProjectNavigation] = useState<Record<string, ProjectNavigation>>(sessionRoute ? { [sessionRoute[1]]: { section: 'Sessions', settingsView: 'General', sessionId: sessionRoute[2] } } : {});
  const projectLeaveGuard = useRef<() => boolean>(() => true);
  const setProjectLeaveGuard = useCallback((guard: () => boolean) => { projectLeaveGuard.current = guard; }, []);
  const navigateProject = useCallback((id: string, value: ProjectNavigation) => setProjectNavigation((previous) => ({ ...previous, [id]: value })), []);
  const [providerView, setProviderView] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selection>({
    group: window.location.hash === '#updates' ? 2 : 0, item: 0, view: 0,
  });
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const groups = navigation;
  const group = groups[selected.group];
  const vmPage = tab === 'System' && group.name === 'Virtual Machines';
  const updatePage = tab === 'System' && group.name === 'Updates';
  const vms = useVms(vmPage);
  const activeVm = vms.vms.find((vm) => vm.id === vmId);
  const componentItems = vmPage ? ['+ New VM', ...vms.vms.map((vm) => vm.name)] : group.items;
  const selectedComponent = vmPage ? (activeVm ? vms.vms.indexOf(activeVm) + 1 : 0) : selected.item;
  const item = componentItems[selectedComponent];
  const providerPage = !vmPage && tab === 'System' && item === 'LLM Provider';
  const providers = useProviders(providerPage);
  const activeProvider = providers.providers.find((provider) => provider.id === providerView);
  const availableViews = vmPage ? (activeVm ? ['Overview', 'Console', 'Settings', 'Exchange', 'Logs'] : []) : providerPage ? ['New Provider', ...providers.providers.map((provider) => provider.name)] : updatePage ? (item === 'Components' ? ['SDK', 'Contract', 'Libraries'] : item === 'Tools' ? ['Zig', 'C', 'Rust', 'QEMU', 'Codex'] : []) : [];
  const selectedView = providerPage ? (activeProvider ? providers.providers.indexOf(activeProvider) + 1 : 0) : selected.view;
  const view = availableViews[selectedView];
  const componentKind: ComponentKind | 'c' | undefined = updatePage && item !== 'R4OS Studio'
    ? ({ SDK: 'sdk', Contract: 'contract', Libraries: 'libraries', Zig: 'zig', C: 'c', Rust: 'rust', QEMU: 'qemu', Codex: 'codex', 'R4OS Releases': 'r4os' } as Record<string, ComponentKind | 'c'>)[view ?? item] : undefined;

  function select(patch: Partial<Selection>) {
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
    if (tab === 'Projects' && value !== tab && !projectLeaveGuard.current()) return false;
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
              <Icon name={name === 'System' ? 'system' : 'folder'} />{name}
            </button>
          ))}
        </div>
      </header>

      <div className="workspace" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === 'Projects' ? <ProjectsWorkspace selectedId={projectId} select={setProjectId}
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
                <button type="button" key={vmPage && index > 0 ? vms.vms[index - 1].id : name} className={`nav-item ${selectedComponent === index ? 'selected' : ''}`}
                  aria-current={selectedComponent === index ? 'true' : undefined}
                  onClick={() => { if (vmPage) setVmId(index ? vms.vms[index - 1].id : null); select({ item: index, view: 0 }); }}>
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
                return <button type="button" key={providerPage ? (provider?.id ?? 'new-provider') : name} className={`nav-item view-item ${selectedView === index ? 'selected' : ''}`}
                  aria-current={selectedView === index ? 'page' : undefined}
                  onClick={() => providerPage ? setProviderView(provider?.id ?? null) : select({ view: index })}>
                  {providerPage ? <>
                    {index === 0 && <span className="view-number" aria-hidden="true">+</span>}
                    <span className="provider-view-name">{name}</span>
                    {provider?.type === 'openai' && provider.status === 'connected' && provider.account &&
                      <span className="provider-remaining" title={remaining == null
                        ? 'Remaining usage is not available.' : 'Lowest reported remaining usage across quota windows.'}>
                        {remaining == null ? '—' : percent(remaining)}
                      </span>}
                  </> : vmPage || updatePage ? <span>{name}</span> : <><span className="view-number">{(index + 1).toString().padStart(2, '0')}</span><span>{name}</span></>}
                </button>;
              })}
            </div>
          </nav>
        </aside>

        <main className="main-area">
          <div className="page-heading"><h1>{vmPage ? (activeVm?.name ?? 'New virtual machine') : (view ?? item)}</h1><span className="page-rule" /></div>
          {updatePage ? componentKind ? <ComponentUpdatesPanel key={componentKind} kind={componentKind} /> : <UpdatesPanel /> : vmPage ? <VmPanel key={activeVm?.id ?? 'new-vm'} api={vms} vm={activeVm} view={view ?? 'Overview'} select={(id) => { setVmId(id); select({ view: 0 }); }} /> : providerPage ? <ProviderPanel provider={activeProvider} api={providers} select={setProviderView} /> : null}
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
