import { useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Icon } from './Icon';
import { navigation, views } from './navigation';
import type { Tab } from './navigation';
import { useProviders } from '../features/llm-providers/useProviders';
import { ProviderPanel } from '../features/llm-providers/components/ProviderPanel';
import { percent } from '../features/llm-providers/usage-format';
import { version } from '../../../shared/version.json';

const tabs: Tab[] = ['System', 'Projects'];
type Selection = { group: number; item: number; view: number };

export function App() {
  const [tab, setTab] = useState<Tab>('System');
  const [providerView, setProviderView] = useState<string | null>(null);
  const [selections, setSelections] = useState<Record<Tab, Selection>>({
    System: { group: 0, item: 0, view: 0 },
    Projects: { group: 0, item: 0, view: 0 },
  });
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = selections[tab];
  const groups = navigation[tab];
  const group = groups[selected.group];
  const item = group.items[selected.item];
  const providerPage = tab === 'System' && item === 'LLM Provider';
  const providers = useProviders(providerPage);
  const activeProvider = providers.providers.find((provider) => provider.id === providerView);
  const availableViews = providerPage ? ['New Provider', ...providers.providers.map((provider) => provider.name)] : views[tab];
  const selectedView = providerPage ? (activeProvider ? providers.providers.indexOf(activeProvider) + 1 : 0) : selected.view;
  const view = availableViews[selectedView];

  function select(patch: Partial<Selection>) {
    setSelections((previous) => ({ ...previous, [tab]: { ...previous[tab], ...patch } }));
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
    setTab(tabs[next]);
    tabRefs.current[next]?.focus();
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
              onClick={() => setTab(name)} onKeyDown={(event) => handleTabKey(event, index)}>
              <Icon name={name === 'System' ? 'system' : 'folder'} />{name}
            </button>
          ))}
        </div>
      </header>

      <div className="workspace" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
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
              {group.items.map((name, index) => (
                <button type="button" key={name} className={`nav-item ${selected.item === index ? 'selected' : ''}`}
                  aria-current={selected.item === index ? 'true' : undefined}
                  onClick={() => select({ item: index, view: 0 })}>
                  <span className="component-mark" /><span>{name}</span>{availableViews.length > 0 && <Icon name="chevron" className="item-chevron" />}
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
                  </> : <><span className="view-number">{(index + 1).toString().padStart(2, '0')}</span><span>{name}</span></>}
                </button>;
              })}
            </div>
          </nav>
        </aside>

        <main className="main-area">
          <div className="content-toolbar">
            <div className="breadcrumb"><span>{tab}</span><Icon name="chevron" /><span>{group.name}</span><Icon name="chevron" /><strong>{item}</strong></div>
            {!providerPage && <span className="placeholder-badge">Placeholder</span>}
          </div>
          <div className="page-heading"><div className="page-eyebrow">{view ? item : group.name}</div><h1>{view ?? item}</h1><span className="page-rule" /></div>
          {providerPage ? <ProviderPanel provider={activeProvider} api={providers} select={setProviderView} /> : <div className="empty-state" key={`${tab}-${group.name}-${item}-${view}`}>
            {view && <>
            <div className="empty-icon"><Icon name={tab === 'System' ? 'system' : 'folder'} /><span className="icon-corner" /></div>
            <span className="empty-eyebrow">IT ALL STARTS HERE</span>
            <h2>Room for your {tab === 'System' ? 'system' : 'projects'}.</h2>
            <p>This view is empty.<br /><span>{item} · {view}</span> will appear here.</p>
            <div className="empty-label"><Icon name="grid" />App shell · Content coming soon</div>
            </>}
          </div>}
        </main>
      </div>

      <footer className="statusbar">
        R4OS Studio | Version {version}
      </footer>
    </div>
  );
}
