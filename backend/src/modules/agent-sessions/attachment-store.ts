import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { componentRoot } from '../components/tools.js';
import { ProjectError } from '../projects/store.js';

/** A fixed helper with binary stdin; never a model or general shell command. */
export function attachmentStore<T>(directory: string, request: Record<string, unknown>, bytes?: Buffer): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/agent-sessions/attachment_cli.py', import.meta.url)),
      directory, componentRoot()], { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false;
    const finish = (error?: Error, value?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(value!);
    };
    const timer = setTimeout(() => { child.kill('SIGKILL'); finish(new ProjectError('The original upload did not respond. Check its receipt before retrying.', 503)); }, 20_000);
    child.on('error', () => finish(new ProjectError('Attachment storage is unavailable.', 503)));
    child.stdin.on('error', () => {});
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      output += chunk;
      if (output.length > 2 * 1024 * 1024) { child.kill('SIGKILL'); finish(new ProjectError('Attachment metadata exceeds the limit.', 503)); }
    });
    child.on('close', () => {
      try {
        const result = JSON.parse(output);
        if (result.error) finish(new ProjectError(result.error, result.code));
        else if (Object.hasOwn(result, 'result')) finish(undefined, result.result as T);
        else finish(new ProjectError('Invalid attachment receipt.', 503));
      } catch { finish(new ProjectError('The original upload is unconfirmed. Check its receipt before retrying.', 503)); }
    });
    child.stdin.write(JSON.stringify(request) + '\n'); child.stdin.end(bytes);
  });
}
