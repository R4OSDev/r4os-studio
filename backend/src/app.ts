import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import { fileURLToPath } from 'node:url';
import { providerRoutes } from './modules/llm-providers/routes.js';
import type { ProviderOptions } from './modules/llm-providers/service.js';

export function createApp({ serveFrontend = false, logger = false, providers = {} }: {
  serveFrontend?: boolean; logger?: boolean; providers?: Partial<ProviderOptions>;
} = {}) {
  const app = Fastify({ logger });

  app.get('/api/health', async () => ({ status: 'ok', service: 'r4os-studio' }));
  app.register(providerRoutes, {
    prefix: '/api/providers',
    directory: process.env.STUDIO_DATA_DIR ?? fileURLToPath(new URL('../../Data/LLMProvider/', import.meta.url)),
    binary: process.env.CODEX_BINARY ?? '/opt/r4os-studio/bin/codex',
    ...providers,
  });

  if (serveFrontend) {
    app.register(fastifyStatic, {
      root: fileURLToPath(new URL('../../frontend/dist', import.meta.url)),
    });
  }

  return app;
}
