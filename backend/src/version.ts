import { readFileSync } from 'node:fs';

// Read the shared source at runtime so TypeScript keeps backend output under dist/.
export const { version } = JSON.parse(
  readFileSync(new URL('../../shared/version.json', import.meta.url), 'utf8'),
) as { version: string };
