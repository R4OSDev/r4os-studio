import { createConnection } from 'node:net';
import type { FastifyInstance } from 'fastify';
import type { ComponentKind, ComponentsStatus } from '../../../../shared/components.js';
import type { UpdateSessions } from './sessions.js';
import { UpdateError } from './client.js';

const kinds: ComponentKind[] = ['sdk', 'contract', 'libraries', 'zig', 'rust', 'qemu', 'codex', 'r4os'];
const identity = { type: 'string', pattern: '^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,127}$' };
function command(value: Record<string, unknown>): Promise<ComponentsStatus> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(process.env.STUDIO_COMPONENT_SOCKET ?? '/run/r4os-studio-components/control.sock');
    let pending = '', settled = false;
    socket.setTimeout(value.command === 'default' && value.kind === 'rust' ? 60_000 : 5_000);
    socket.on('connect', () => socket.write(JSON.stringify(value) + '\n'));
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (settled) return;
      if (pending.length > 2 * 1024 * 1024) { socket.destroy(new Error('Oversized response')); return; }
      if (!pending.includes('\n')) return;
      settled = true; socket.end();
      try {
        const response = JSON.parse(pending.split('\n')[0]);
        if (response.error) reject(new UpdateError(response.error, response.code ?? 409));
        else if (response.status?.components) resolve(response.status);
        else reject(new UpdateError('The component service returned an invalid response.'));
      } catch { reject(new UpdateError('The component service returned an invalid response.')); }
    });
    socket.on('timeout', () => socket.destroy(new Error('Timeout')));
    socket.on('error', () => reject(new UpdateError('The component host service is unavailable.')));
    socket.on('end', () => { if (!settled) reject(new UpdateError('The component service disconnected.')); });
  });
}

export async function componentRoutes(app: FastifyInstance, sessions: UpdateSessions) {
  app.get('/components', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    const status = await command({ command: 'status' }).catch((): ComponentsStatus => ({
      enabled: false, components: Object.fromEntries(kinds.map((kind) => [kind, {
        installed: [], available: [], activeId: null, latestId: null, checkedAt: null, error: null, hasMore: false,
      }])) as unknown as ComponentsStatus['components'], job: null,
      message: 'Component host support is not configured. A host administrator must install the component service.',
    }));
    return { ...status, csrfToken: session.token };
  });
  for (const action of ['check', 'download', 'default']) {
    app.post<{ Body: { kind: ComponentKind; id?: string; older?: boolean } }>(`/components/${action}`, {
      preValidation: async (request) => {
        const allowed = action === 'check' ? ['kind', 'older'] : ['kind', 'id'];
        if (request.body && typeof request.body === 'object' && Object.keys(request.body).some((key) => !allowed.includes(key))) {
          throw new UpdateError('Unexpected component request fields.', 400);
        }
      },
      schema: { body: { type: 'object', additionalProperties: false,
        required: action === 'check' ? ['kind'] : ['kind', 'id'],
        properties: { kind: { type: 'string', enum: kinds }, ...(action === 'check' ? { older: { type: 'boolean' } } : { id: identity }) },
      } },
    }, async (request, reply) => {
      sessions.mutation(request, reply);
      return reply.code(action === 'default' ? 200 : 202).send(await command({ command: action, ...request.body }));
    });
  }
}
