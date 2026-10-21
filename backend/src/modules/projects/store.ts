import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ProjectSummary } from '../../../../shared/projects.js';

// Releases share the persistent data root already configured for R4OS components.
export function projectsDirectory() {
  return process.env.STUDIO_R4OS_DIR
    ? join(process.env.STUDIO_R4OS_DIR, '..', 'Projects')
    : fileURLToPath(new URL('../../../../Data/Projects/', import.meta.url));
}

export async function listProjects(directory: string): Promise<ProjectSummary[]> {
  try {
    const entries = await readdir(directory, { withFileTypes: true });
    return entries.filter((entry) => entry.isDirectory())
      .map((entry) => ({ id: entry.name, name: entry.name }))
      .sort((left, right) => left.name.localeCompare(right.name, 'en', { numeric: true }));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return [];
    throw error;
  }
}
