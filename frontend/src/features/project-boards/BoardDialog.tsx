import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

export function BoardDialog({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null), titleId = useId();
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal(); element.querySelector<HTMLInputElement>('input,select,textarea')?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected && !opener.matches(':disabled')) opener.focus(); };
  }, []);
  return createPortal(<dialog className="project-dialog board-dialog" ref={dialog} aria-labelledby={titleId} onCancel={event => { event.preventDefault(); close(); }}>
    <header className="project-dialog-header"><h2 id={titleId}>{title}</h2></header>{children}
  </dialog>, document.body);
}
