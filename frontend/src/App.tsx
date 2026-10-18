import { useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Icon } from './Icon';
import { navigation, views } from './navigation';
import type { Tab } from './navigation';

const tabs: Tab[] = ['System', 'Projects'];
type Selection = { group: number; item: number; view: number };

export function App() {
  const [tab, setTab] = useState<Tab>('System');
  const [selections, setSelections] = useState<Record<Tab, Selection>>({
    System: { group: 0, item: 0, view: 0 },
    Projects: { group: 0, item: 0, view: 0 },
  });
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = selections[tab];
  const groups = navigation[tab];
  const group = groups[selected.group];
  const item = group.items[selected.item];
  const view = views[selected.view];

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
        <a className="brand" href="/" aria-label="R4OS Studio Startseite">
          <span className="brand-mark"><Icon name="terminal" /></span>
          <span>R4OS <span className="brand-light">Studio</span></span>
        </a>
        <div className="tabs" role="tablist" aria-label="Arbeitsbereiche">
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
        <span className="stage-label">WORKSPACE <span>01</span></span>
      </header>

      <div className="workspace" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        <aside className="navigation" aria-label={`${tab}-Navigation`}>
          <nav className="nav-column" aria-label="Bereiche">
            <div className="column-heading"><span>Bereiche</span><span className="count">{groups.length.toString().padStart(2, '0')}</span></div>
            <div className="nav-items">
              {groups.map((entry, index) => (
                <button type="button" key={entry.name} className={`nav-item ${selected.group === index ? 'selected' : ''}`}
                  aria-current={selected.group === index ? 'true' : undefined}
                  onClick={() => select({ group: index, item: 0, view: 0 })}>
                  <Icon name={entry.icon} /><span>{entry.name}</span><Icon name="chevron" className="item-chevron" />
                </button>
              ))}
            </div>
            <div className="column-note"><span className="small-dot" />{tab === 'System' ? 'Systemverwaltung' : 'Projektverwaltung'}</div>
          </nav>
          <nav className="nav-column" aria-label="Komponenten">
            <div className="column-heading"><span>Komponenten</span><span className="count">{group.items.length.toString().padStart(2, '0')}</span></div>
            <div className="nav-context">{group.name}</div>
            <div className="nav-items compact">
              {group.items.map((name, index) => (
                <button type="button" key={name} className={`nav-item ${selected.item === index ? 'selected' : ''}`}
                  aria-current={selected.item === index ? 'true' : undefined}
                  onClick={() => select({ item: index, view: 0 })}>
                  <span className="component-mark" /><span>{name}</span><Icon name="chevron" className="item-chevron" />
                </button>
              ))}
            </div>
          </nav>
          <nav className="nav-column" aria-label="Ansichten">
            <div className="column-heading"><span>Ansichten</span><span className="count">03</span></div>
            <div className="nav-context">{item}</div>
            <div className="nav-items compact">
              {views.map((name, index) => (
                <button type="button" key={name} className={`nav-item view-item ${selected.view === index ? 'selected' : ''}`}
                  aria-current={selected.view === index ? 'page' : undefined}
                  onClick={() => select({ view: index })}>
                  <span className="view-number">0{index + 1}</span><span>{name}</span>
                </button>
              ))}
            </div>
          </nav>
        </aside>

        <main className="main-area">
          <div className="content-toolbar">
            <div className="breadcrumb"><span>{tab}</span><Icon name="chevron" /><span>{group.name}</span><Icon name="chevron" /><strong>{item}</strong></div>
            <span className="placeholder-badge">Platzhalter</span>
          </div>
          <div className="page-heading"><div className="page-eyebrow">{item}</div><h1>{view}</h1><span className="page-rule" /></div>
          <div className="empty-state" key={`${tab}-${group.name}-${item}-${view}`}>
            <div className="empty-icon"><Icon name={tab === 'System' ? 'system' : 'folder'} /><span className="icon-corner" /></div>
            <span className="empty-eyebrow">ALLES BEGINNT HIER</span>
            <h2>Raum für {tab === 'System' ? 'dein System' : 'deine Projekte'}.</h2>
            <p>Diese Ansicht ist noch leer.<br />Hier entsteht <span>{item} · {view}</span>.</p>
            <div className="empty-label"><Icon name="grid" />Grundgerüst · Inhalte folgen</div>
          </div>
          <div className="main-footnote"><span>R4OS Entwicklungsumgebung</span><span>APP SHELL / 0.1</span></div>
        </main>
      </div>

      <footer className="statusbar">
        <div><span className="status-indicator" />UI bereit<span className="status-divider" />{tab}<span className="status-slash">/</span>{view}</div>
        <span>Lokales Grundgerüst<span className="status-divider" />R4OS Studio</span>
      </footer>
    </div>
  );
}
