import type { FastifyInstance } from 'fastify';
import { createServer, type Socket } from 'node:net';
import { spawn } from 'node:child_process';
import { chmod, lstat, readFile, unlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';
import { projectsDirectory } from '../projects/store.js';
import { root, validId, VmError } from '../virtual-machines/paths.js';
import type { VmManager } from '../virtual-machines/service.js';
import type { ConsoleBridge } from '../virtual-machines/console.js';
import type { PointerControllers } from '../virtual-machines/pointer.js';
import { qmp } from '../virtual-machines/qmp.js';
import { exec } from '../virtual-machines/systemd.js';

interface Lease {
  id: string; vmId: string;
  scope: { kind: 'access' | 'job' | 'recovery'; projectId?: string; projectRevision?: number;
    vmRevision: string; imageId: string; imageSha256: string; bootId?: string };
}

function inspectLease(leaseId: string, token: string, checkBoot = true): Promise<Lease> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/project-development/lease.py', import.meta.url)),
      'inspect', projectsDirectory()], { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let data = '';
    const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new VmError('VM reservation validation timed out.', 503)); }, 5000);
    child.stdin.on('error', () => {}); child.on('error', () => { clearTimeout(timer); reject(new VmError('VM reservation support is unavailable.', 503)); });
    child.stdout.on('data', (part) => { data += part.toString(); if (data.length > 16384) child.kill('SIGKILL'); });
    child.on('close', () => {
      clearTimeout(timer);
      try { const value = JSON.parse(data); if (value.error) reject(new VmError(value.error, value.code)); else resolve(value.result); }
      catch { reject(new VmError('Invalid VM reservation response.', 503)); }
    });
    child.stdin.end(JSON.stringify({ leaseId, token, checkBoot }));
  });
}

/** Private bridge: operations are derived from a held, durable VM reservation. */
export function developmentVmBridge(app: FastifyInstance, manager: VmManager, consoles: ConsoleBridge, pointers: PointerControllers) {
  if (process.env.STUDIO_DEVELOPMENT_BRIDGE_ENABLED !== '1') return;
  const path = process.env.STUDIO_DEVELOPMENT_VM_SOCKET ?? '/run/r4os-studio-development/vm.sock';
  const peers = new Set<Socket>();
  const server = createServer({ allowHalfOpen: true }, (socket) => {
    peers.add(socket); socket.setEncoding('utf8'); socket.setTimeout(15000, () => socket.destroy());
    let pending = '', admitted = false;
    socket.on('close', () => peers.delete(socket)); socket.on('error', () => {});
    socket.on('data', (part) => {
      if (admitted) return;
      pending += part;
      if (pending.length > 16384) { socket.destroy(); return; }
      if (!pending.includes('\n')) return;
      admitted = true;
      void (async () => {
        try {
          const request = JSON.parse(pending.split('\n')[0]);
          if (!request || typeof request !== 'object' || Object.keys(request).some((k) => !['operation', 'leaseId', 'token', 'port'].includes(k))
            || !validId(request.leaseId) || !/^[a-f0-9]{64}$/.test(request.token)) throw new VmError('Invalid private VM request.', 400);
          if (!['info', 'start', 'forward_open', 'forward_close', 'capture'].includes(request.operation)) throw new VmError('Unsupported private VM operation.', 400);
          const lease = await inspectLease(request.leaseId, request.token, request.operation !== 'forward_close'), id = lease.vmId;
          const config = await manager.config(id), scope = lease.scope;
          if ((config.revision ?? config.imageSha256) !== scope.vmRevision || config.imageId !== scope.imageId || config.imageSha256 !== scope.imageSha256)
            throw new VmError('The reserved VM configuration or image changed.');
          if (scope.kind === 'job') {
            const { projectStore } = await import('../projects/store.js');
            const project = await projectStore<{ vmId: string | null; revision: number }>(projectsDirectory(), { operation: 'get', id: scope.projectId });
            if (project.vmId !== id || project.revision !== scope.projectRevision) throw new VmError('The project VM assignment changed.');
          }
          if (scope.bootId && request.operation !== 'forward_close') {
            const boot = JSON.parse(await readFile(join(projectsDirectory(), '.studio/development/Boots', id + '.json'), 'utf8'));
            if (!boot.connected || boot.bootId !== scope.bootId || boot.vmRevision !== scope.vmRevision) throw new VmError('The guest boot binding changed.');
          }
          let result: unknown;
          if (request.operation === 'info') {
            const { stdout } = await exec('/usr/bin/systemctl', ['show', `r4os-studio-vm@${id}.service`, '--property=InvocationID', '--value'], { timeout: 5000 });
            result = { vm: await manager.get(id), invocationId: stdout.trim() };
          } else if (request.operation === 'capture') {
            const limits = JSON.parse(await readFile(new URL('../../../../shared/development-host.json', import.meta.url), 'utf8')).limits;
            const data = await manager.screen(id, limits.screenshotBytes);
            result = { base64: data.toString('base64') };
          } else {
            consoles.closeVm(id); await pointers.closeVm(id);
            if (request.operation === 'start') result = { vm: await manager.action(id, 'start') };
            else {
              if (!config.networkEnabled) throw new VmError('Enable Network explicitly in VM settings before using development access.');
              if (!Number.isInteger(request.port) || request.port < 1024 || request.port > 65535) throw new VmError('Invalid private forwarding port.', 400);
              const command = request.operation === 'forward_open'
                ? `hostfwd_add studio-net tcp:127.0.0.1:${request.port}-:22`
                : `hostfwd_remove studio-net tcp:127.0.0.1:${request.port}`;
              const response: unknown = await qmp(id, 'human-monitor-command', { 'command-line': command });
              const removal = `host forwarding rule for tcp:127.0.0.1:${request.port} `;
              // QEMU reports successful removal as text; a missing exact rule
              // is the idempotent result after a lost removal response.
              const removed = request.operation === 'forward_close' && typeof response === 'string'
                && [removal + 'removed', removal + 'not found'].includes(response.trim());
              if (typeof response !== 'string' || (response.trim() && !removed)) throw new VmError('The private guest forwarding operation failed.');
              result = { configured: true };
            }
          }
          socket.end(JSON.stringify({ result }) + '\n');
        } catch (error) {
          socket.end(JSON.stringify({ error: error instanceof VmError ? error.message : 'The private VM bridge is unavailable.', code: error instanceof VmError ? error.statusCode : 503 }) + '\n');
        }
      })();
    });
  });
  app.addHook('onReady', async () => {
    // Explicit production support must bind the same data root as this release.
    const config = JSON.parse(await readFile('/etc/r4os-studio-development/config.json', 'utf8'));
    if (resolve(config.r4os) !== resolve(root) || resolve(config.projects) !== resolve(projectsDirectory())) throw new VmError('Development bridge data roots do not match.', 503);
    try { const info = await lstat(path); if (!info.isSocket()) throw new VmError('Invalid private VM bridge path.', 503); await unlink(path); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(path, resolve); });
    await chmod(path, 0o600);
  });
  app.addHook('preClose', async () => { for (const peer of peers) peer.destroy(); });
  app.addHook('onClose', async () => {
    await new Promise<void>((resolve) => server.close(() => resolve())); await unlink(path).catch(() => {});
  });
}
