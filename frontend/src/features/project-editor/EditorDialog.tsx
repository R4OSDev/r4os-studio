import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export function EditorDialog({ label, busy = false, close, children }: {
  label: string; busy?: boolean; close: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current!, opener = document.activeElement;
    element.showModal();
    const input = element.querySelector<HTMLInputElement>('input:not(:disabled)');
    if (input) { input.focus(); input.select(); } else element.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  return <dialog className="editor-dialog" ref={ref} aria-label={label} tabIndex={-1}
    onCancel={(event) => { event.preventDefault(); if (!busy) close(); }}>{children}</dialog>;
}
