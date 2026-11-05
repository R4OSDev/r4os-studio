import type { ReactNode } from 'react';
import { Icon } from '../../app/Icon';
import './styles.css';

export function StatusWorkspace({ children }: { children: ReactNode }) {
  return <>
    <aside className="navigation status-navigation" aria-label="Status navigation">
      <nav className="nav-column" aria-label="Areas">
        <div className="column-heading">Areas</div>
        <div className="nav-items">
          <a className="nav-item selected" href="#status/ai-limits" aria-current="page"><Icon name="statistics" /><span>AI Limits</span></a>
        </div>
      </nav>
    </aside>
    <main className="main-area">
      <div className="page-heading"><h1>AI Limits</h1><span className="page-rule" /></div>
      <div className="status-content">{children}</div>
    </main>
  </>;
}
