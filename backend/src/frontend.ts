import type { FastifyInstance } from 'fastify';
import fastifyStatic from '@fastify/static';
import { relative, sep } from 'node:path';

export function registerFrontend(app: FastifyInstance, root: string) {
  app.register(fastifyStatic, {
    root,
    preCompressed: true,
    maxAge: 0,
    setHeaders(reply, path) {
      const name = relative(root, path).split(sep).join('/').replace(/\.(br|gz)$/, '');
      const route = reply.request.routeOptions.url ?? '';
      if (name === '..' || name.startsWith('../') || route === '/api' || route.startsWith('/api/') || reply.request.url.startsWith('/api/')) {
        reply.header('Cache-Control', 'no-store'); return;
      }
      const hashed = /^assets\/(?:[^/]+\/)*[^/]+-[A-Za-z0-9_-]{8,}\.(?:js|mjs|css|woff2?|ttf|otf|svg|png|jpe?g|webp|avif|ico|wasm)$/.test(name);
      reply.header('Cache-Control', hashed ? 'public, max-age=31536000, immutable' : 'no-cache');
    },
  });
}
