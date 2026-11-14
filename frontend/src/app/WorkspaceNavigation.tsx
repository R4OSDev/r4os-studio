import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import type { FocusEvent, ReactNode } from 'react';
import { Icon } from './Icon';

const narrowViewport = window.matchMedia('(max-width: 1050px)');
const isNarrow = () => narrowViewport.matches;
function watchViewport(change: () => void) {
  narrowViewport.addEventListener('change', change);
  return () => narrowViewport.removeEventListener('change', change);
}

export function WorkspaceNavigation({ label, fixed = false, className = '', children }: {
  label: string; fixed?: boolean; className?: string; children: ReactNode;
}) {
  const narrow = useSyncExternalStore(watchViewport, isNarrow) && !fixed;
  const [layout, setLayout] = useState({ narrow, open: false });
  if (layout.narrow !== narrow) setLayout({ narrow, open: false });
  const open = narrow && layout.narrow === narrow && layout.open;
  const panelId = useId();
  const region = useRef<HTMLDivElement>(null), grip = useRef<HTMLButtonElement>(null);
  const draggingInside = useRef(false);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (draggingInside.current || event.target instanceof Node && region.current?.contains(event.target)) return;
      setLayout({ narrow: true, open: false });
    }
    document.addEventListener('pointerdown', dismiss, true);
    return () => document.removeEventListener('pointerdown', dismiss, true);
  }, [open]);

  function leaveFocus(event: FocusEvent) {
    if (draggingInside.current || event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
    setLayout({ narrow: true, open: false });
  }

  return <div className={fixed ? 'workspace-navigation' : 'workspace-navigation collapsible-navigation'} ref={region}
    onDragStart={event => { if (open && !event.defaultPrevented) draggingInside.current = true; }}
    onDragEnd={() => { draggingInside.current = false; }}
    onPointerLeave={event => {
      if (!open || draggingInside.current || event.pointerType !== 'mouse') return;
      if (document.activeElement instanceof HTMLElement && event.currentTarget.contains(document.activeElement))
        document.activeElement.blur();
      setLayout({ narrow: true, open: false });
    }}
    onBlur={open ? leaveFocus : undefined}
    onKeyDown={event => {
      if (!open || event.key !== 'Escape' || event.defaultPrevented) return;
      event.preventDefault();
      grip.current?.focus({ preventScroll: true });
      setLayout({ narrow: true, open: false });
    }}>
    <button type="button" className="navigation-grip" ref={grip} aria-label={open ? 'Close navigation' : 'Open navigation'}
      title={open ? 'Close navigation' : 'Open navigation'} aria-controls={panelId} aria-expanded={open}
      onPointerEnter={event => {
        if (narrow && event.pointerType === 'mouse') setLayout({ narrow: true, open: true });
      }}
      onClick={() => setLayout({ narrow: true, open: !open })}>
      <Icon name="chevron" />
    </button>
    <aside id={panelId} className={`navigation ${className}`} aria-label={label} inert={narrow && !open}>{children}</aside>
  </div>;
}
