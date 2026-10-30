type IconName = 'system' | 'box' | 'book' | 'flask' | 'folder' | 'settings' | 'chevron' | 'grid' | 'terminal' | 'play' | 'pause' | 'restart' | 'power' | 'stop' | 'attachment' | 'board' | 'statistics' | 'note' | 'image';

const paths: Record<IconName, React.ReactNode> = {
  image:<><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/></>,
  note: <><path d="M14 3H5v18h14V8Z" /><path d="M14 3v5h5M8 12h8M8 16h5" /></>,
  statistics: <><path d="M4 20h16M6 16v-5M12 16V5M18 16V8" /></>,
  board: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 4v16M5.5 8h1M11.5 8h1M17.5 8h1" /></>,
  attachment: <path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2a2 2 0 0 1 3 3L6 15a1 1 0 0 0 2 2l8-8" />,
  play: <path d="m8 4 13 8-13 8Z" />,
  pause: <><path d="M8 5v14M16 5v14" /></>,
  restart: <><path d="M20 7v5h-5M20 12a8 8 0 1 0-2 5M20 7l-3 3" /></>,
  power: <><path d="M12 2v10M6 5a9 9 0 1 0 12 0" /></>,
  stop: <rect x="5" y="5" width="14" height="14" rx="1" />,
  system: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" /></>,
  box: <><path d="m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 9 9-4M12 12 3 8m9 4v9M7.5 5.5l9 5" /></>,
  book: <><path d="M12 5v15M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v15h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z" /></>,
  flask: <><path d="M9 3h6m-5 0v6L4 19a1.3 1.3 0 0 0 1 2h14a1.3 1.3 0 0 0 1-2L14 9V3M7 14h10" /></>,
  folder: <path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  settings: <><path d="M3 7h6m4 0h8M3 17h12m4 0h2" /><circle cx="11" cy="7" r="2" /><circle cx="17" cy="17" r="2" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  terminal: <path d="m5 6 6 6-6 6m9 0h6" />,
};

export function Icon({ name, className = '', energyPulse = false }: { name: IconName; className?: string; energyPulse?: boolean }) {
  return <svg className={`icon ${className} ${name === 'folder' && energyPulse ? 'project-folder-active' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}
    {name === 'folder' && energyPulse && <g><g className="project-folder-fill">{paths.folder}</g><g className="project-folder-light">{paths.folder}</g></g>}
  </svg>;
}
