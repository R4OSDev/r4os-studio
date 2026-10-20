import Fastify from 'fastify';
import { vmRoutes } from './modules/virtual-machines/routes.js';
import fastifyStatic from '@fastify/static';
import { fileURLToPath } from 'node:url';
import { providerRoutes } from './modules/llm-providers/routes.js';
import type { ProviderOptions } from './modules/llm-providers/service.js';
import { updateRoutes } from './modules/updates/routes.js';
import { version } from './version.js';
import { activeTool } from './modules/components/tools.js';

export function createApp({ serveFrontend = false, logger = false, providers = {} }: {
  serveFrontend?: boolean; logger?: boolean; providers?: Partial<ProviderOptions>;
} = {}) {
  const app = Fastify({ logger });

  app.get('/api/health', async () => ({ status: 'ok', service: 'r4os-studio', version,
    release: process.env.STUDIO_RELEASE_ID ?? null }));
  app.register(providerRoutes, {
    prefix: '/api/providers',
    directory: process.env.STUDIO_DATA_DIR ?? fileURLToPath(new URL('../../Data/LLMProvider/', import.meta.url)),
    binary: process.env.CODEX_BINARY ?? '/opt/r4os-studio/bin/codex',
    ...(!process.env.CODEX_BINARY && !providers.binary ? { binaryResolver: async () => (await activeTool('codex')).binary } : {}),
    ...providers,
  });

  app.register(vmRoutes, { prefix: '/api/vms' });
  app.register(updateRoutes, { prefix: '/api/updates' });

  if (serveFrontend) {
    app.register(fastifyStatic, {
      root: fileURLToPath(new URL('../../frontend/dist', import.meta.url)),
    });
  }

  return app;
}
