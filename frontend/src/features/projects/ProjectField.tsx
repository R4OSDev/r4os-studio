import type { ReactNode } from 'react';

export function ProjectField({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return <div className="project-field"><label htmlFor={id}>{label}</label>{children}</div>;
}
