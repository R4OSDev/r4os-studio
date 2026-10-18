import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import { fileURLToPath } from 'node:url';

export function createApp({ serveFrontend = false, logger = false } = {}) {
  const app = Fastify({ logger });

  app.get('/api/health', async () => ({ status: 'ok', service: 'r4os-studio' }));

  if (serveFrontend) {
    app.register(fastifyStatic, {
      root: fileURLToPath(new URL('../../frontend/dist', import.meta.url)),
    });
  }

  return app;
}
