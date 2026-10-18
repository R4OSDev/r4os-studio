import { createApp } from './app.js';

const serveFrontend = process.argv.includes('--serve-frontend');
const app = createApp({ serveFrontend, logger: true });
const host = process.env.HOST ?? (serveFrontend ? '0.0.0.0' : '127.0.0.1');
const port = Number(process.env.PORT ?? (serveFrontend ? 5010 : 3001));

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('PORT muss eine ganze Zahl zwischen 1 und 65535 sein.');
}

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    void app.close().catch((error: unknown) => {
      app.log.error(error);
      process.exitCode = 1;
    });
  });
}

try {
  await app.listen({ host, port });
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
}
