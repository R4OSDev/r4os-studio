import { connect } from 'node:net';
import { ProjectError } from '../projects/store.js';

/** Fixed protocol over a private peer-checked Unix socket; never a shell bridge. */
export function developmentHost<T>(request: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const socket = connect(process.env.STUDIO_DEVELOPMENT_SOCKET ?? '/run/r4os-studio-development/host.sock');
    socket.setEncoding('utf8');
    let pending = '', settled = false;
    const finish = (error?: Error, result?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer); socket.destroy();
      if (error) reject(error); else resolve(result!);
    };
    const timer = setTimeout(() => finish(new ProjectError('The development coordinator did not respond.', 503)), ['github_import_finish', 'github_pull_validate'].includes(String(request.operation)) ? 190_000 : 25_000);
    socket.on('error', () => finish(new ProjectError('Development host support is unavailable.', 503)));
    socket.on('connect', () => socket.end(JSON.stringify(request) + '\n'));
    socket.on('data', (part) => {
      pending += part.toString();
      if (pending.length > 2 * 1024 * 1024) return finish(new ProjectError('Development response exceeds the limit.', 503));
      if (!pending.includes('\n')) return;
      try {
        const value = JSON.parse(pending.split('\n')[0]);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result as T);
        else finish(new ProjectError('Invalid development coordinator response.', 503));
      } catch { finish(new ProjectError('Invalid development coordinator response.', 503)); }
    });
    socket.on('end', () => { if (!settled) finish(new ProjectError('Development coordinator connection closed.', 503)); });
  });
}
