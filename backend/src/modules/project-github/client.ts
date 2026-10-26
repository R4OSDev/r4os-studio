import { connect } from 'node:net';
import { ProjectError } from '../projects/store.js';

export function gitHost<T>(request: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const socket = connect(process.env.STUDIO_GIT_SOCKET ?? '/run/r4os-studio-git/control.sock');
    let output = '', done = false;
    const finish = (error?: Error, result?: T) => {
      if (done) return; done = true; clearTimeout(timer); socket.destroy();
      if (error) reject(error); else resolve(result!);
    };
    const timer = setTimeout(() => finish(new ProjectError('Git host did not respond. Recheck the original request before retrying.', 503)), 10_000);
    socket.setEncoding('utf8');
    socket.on('connect', () => socket.end(JSON.stringify(request) + '\n'));
    socket.on('error', () => finish(new ProjectError('Git host support is unavailable.', 503)));
    socket.on('data', (chunk: string) => {
      output += chunk;
      if (output.length > 2 * 1024 * 1024) return finish(new ProjectError('Git response exceeded its limit.', 503));
      if (!output.includes('\n')) return;
      try { const value = JSON.parse(output.split('\n')[0]);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result as T);
        else finish(new ProjectError('Git response is invalid.', 503));
      } catch { finish(new ProjectError('Git response is invalid.', 503)); }
    });
    socket.on('end', () => { if (!done) finish(new ProjectError('Git host closed without a receipt. Check the original request.', 503)); });
  });
}
