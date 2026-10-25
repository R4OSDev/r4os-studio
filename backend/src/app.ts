import Fastify from 'fastify';
import { vmRoutes } from './modules/virtual-machines/routes.js';
import fastifyStatic from '@fastify/static';
import { fileURLToPath } from 'node:url';
import { providerRoutes } from './modules/llm-providers/routes.js';
import type { ProviderOptions } from './modules/llm-providers/service.js';
import { updateRoutes } from './modules/updates/routes.js';
import { version } from './version.js';
import { activeTool } from './modules/components/tools.js';
import { projectRoutes } from './modules/projects/routes.js';
import { projectsDirectory } from './modules/projects/store.js';
import { cancelProviderRuns } from './modules/agent-sessions/host.js';
import { settingsRoutes } from './modules/settings/routes.js';
import { dirname, join } from 'node:path';
import { githubRoutes } from './modules/github-connections/routes.js';
import type { GitHubTestResult } from '../../shared/github-connections.js';

export function createApp({ serveFrontend = false, logger = false, providers = {}, projectDirectory = projectsDirectory(), githubTester }: {
  serveFrontend?: boolean; logger?: boolean; providers?: Partial<ProviderOptions>; projectDirectory?: string;
  githubTester?: (token: string) => Promise<GitHubTestResult>;
} = {}) {
  const app = Fastify({ logger });
  const legacyCodex = '/opt/r4os-studio/bin/codex';
  const codexOverride = process.env.CODEX_BINARY;
  // Old installers set the fallback path explicitly before selectable tools
  // existed. Keep that deployment compatible with the selected default.
  const selectedCodex = (!codexOverride || codexOverride === legacyCodex) && !providers.binary;

  app.get('/api/health', async () => ({ status: 'ok', service: 'r4os-studio', version,
    release: process.env.STUDIO_RELEASE_ID ?? null }));
  app.register(providerRoutes, {
    prefix: '/api/providers',
    beforeDisconnect: (id: string) => cancelProviderRuns(projectDirectory, id),
    directory: process.env.STUDIO_DATA_DIR ?? fileURLToPath(new URL('../../Data/LLMProvider/', import.meta.url)),
    binary: codexOverride || legacyCodex,
    ...(selectedCodex ? { binaryResolver: async () => (await activeTool('codex')).binary } : {}),
    ...providers,
  });

  app.register(vmRoutes, { prefix: '/api/vms' });
  app.register(updateRoutes, { prefix: '/api/updates' });
  app.register(projectRoutes, { prefix: '/api/projects', directory: projectDirectory, providerDirectory: providers.directory });
  app.register(settingsRoutes, { prefix: '/api/settings', directory: projectDirectory });
  app.register(githubRoutes, { prefix: '/api/github', directory: join(dirname(providers.directory ?? process.env.STUDIO_DATA_DIR
    ?? fileURLToPath(new URL('../../Data/LLMProvider/', import.meta.url))), 'GitHub'), tester: githubTester });

  if (serveFrontend) {
    app.register(fastifyStatic, {
      root: fileURLToPath(new URL('../../frontend/dist', import.meta.url)),
    });
  }

  return app;
}
