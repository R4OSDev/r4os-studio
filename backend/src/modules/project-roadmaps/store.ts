import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { StringDecoder } from 'node:string_decoder';
import { lstat, realpath } from 'node:fs/promises';
import { ProjectError } from '../projects/store.js';

function execute<T>(directory: string, request: { operation: string; projectId: string; [key: string]: unknown }, mode: 'full' | 'probe' = 'full'): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/project-roadmaps/cli.py', import.meta.url)), directory, ...(mode === 'probe' ? ['--revision-probe'] : ['read','overview','list','get','notes','current','revision'].includes(request.operation) ? ['--verified-read'] : [])],
      { detached: true, stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', outputBytes = 0, settled = false;
    const decoder = new StringDecoder('utf8');
    const finish = (error?: Error, result?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(result!);
    };
    const terminate = () => {
      try { if (child.pid) process.kill(-child.pid, 'SIGKILL'); } catch { child.kill('SIGKILL'); }
    };
    const timer = setTimeout(() => { terminate(); finish(new ProjectError('The roadmap service did not respond.')); }, ['export','json_export','import_preview','import_apply'].includes(request.operation) ? 30_000 : 10_000);
    child.on('error', () => finish(new ProjectError('Roadmap storage is unavailable.')));
    child.stdin.on('error', () => { /* The close event handles rejected input. */ });
    child.stdout.on('data', (chunk: Buffer) => {
      outputBytes += chunk.length;
      output += decoder.write(chunk);
      if (outputBytes > 2 * 1024 * 1024) {
        terminate(); finish(new ProjectError('The roadmap response is too large.', 413));
      }
    });
    child.on('close', () => {
      try {
        output += decoder.end();
        const value = JSON.parse(output);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value as T);
        else finish(new ProjectError('Roadmap storage returned an invalid response.'));
      } catch { finish(new ProjectError('Roadmap storage is unavailable.')); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}


type Binding = { revision: number; currentVersionId: string };
type FileFact = { path: string; kind: 'directory' | 'file' | 'control'; signature: string[] | null };
type Generation = { projectId: string; binding: Binding; files: FileFact[] };
type Envelope<T> = { result: T; generation?: Generation };
type Verified = { generation: Generation; expires: number };
const verified = new Map<string, Verified>();
const readOperations = new Set(['read','overview','list','get','notes','current','revision']);
async function matches(generation: Generation) {
  if (!Array.isArray(generation.files) || generation.files.length !== 13) return false;
  try {
    for (const fact of generation.files) {
      let info;
      try { info = await lstat(fact.path, { bigint: true }); }
      catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT' && fact.signature === null) continue; return false; }
      if (!fact.signature || await realpath(fact.path) !== fact.path || (fact.kind === 'directory' ? !info.isDirectory() : !info.isFile() || info.nlink !== 1n)) return false;
      const values = [info.dev, info.ino, info.mode, info.uid];
      if (fact.kind !== 'directory') values.push(info.nlink);
      if (fact.kind === 'file') values.push(info.size, info.mtimeNs, info.ctimeNs);
      else if (fact.kind === 'control') values.push(info.size);
      if (JSON.stringify(values.map(String)) !== JSON.stringify(fact.signature)) return false;
    }
    return true;
  } catch { return false; }
}
function decorate<T>(result: T, generation?: Generation): T {
  if (!generation || !result || typeof result !== 'object') return result;
  // This opaque data-generation marker reaches each browser. A shared cache
  // update in another browser must not conceal a replacement at equal revision.
  const sourceGeneration = createHash('sha256').update(JSON.stringify(generation.files.filter(fact => /\/Roadmap(?:\/Roadmap\.sqlite(?:-(?:journal|wal))?)?$/.test(fact.path)))).digest('hex');
  const value = result as Record<string, unknown>;
  if (typeof value.revision === 'number' && typeof value.currentVersionId === 'string') return { ...value, sourceGeneration } as T;
  if (value.exists && value.roadmap) return { ...value, sourceGeneration,
    ...(value.versions ? { versions: { ...(value.versions as object), sourceGeneration } } : {}) } as T;
  return result;
}
export async function roadmapStore<T>(directory: string, request: { operation: string; projectId: string; [key: string]: unknown }): Promise<T> {
  const key = directory + '\0' + request.projectId, previous = verified.get(key), read = readOperations.has(request.operation);
  if (!read) verified.delete(key);
  const unchanged = request.operation === 'revision' && previous ? await matches(previous.generation) : false;
  if (unchanged && previous!.expires > Date.now() && verified.get(key) === previous) {
    const probe = await execute<Envelope<Binding>>(directory, request, 'probe').catch(error => { verified.delete(key); throw error; });
    if (!Number.isSafeInteger(probe.result?.revision) || typeof probe.result?.currentVersionId !== 'string') { verified.delete(key); throw new ProjectError('The roadmap revision could not be verified.', 503); }
    if (verified.get(key) === previous && await matches(previous!.generation)
      && probe.result.revision === previous!.generation.binding.revision && probe.result.currentVersionId === previous!.generation.binding.currentVersionId)
      return decorate(probe.result, previous!.generation) as T;
    verified.delete(key);
  }
  const envelope = await execute<Envelope<T>>(directory, request).catch(error => { verified.delete(key); throw error; });
  const generation = envelope.generation;
  let attested: Generation | undefined;
  if (read && generation?.projectId === request.projectId && Number.isSafeInteger(generation.binding?.revision) && typeof generation.binding.currentVersionId === 'string' && await matches(generation)) {
    attested = generation;
    for (const [oldKey, entry] of verified) if (entry.expires <= Date.now()) verified.delete(oldKey);
    verified.delete(key); verified.set(key, { generation, expires: Date.now() + 30000 });
    while (verified.size > 64) verified.delete(verified.keys().next().value!);
  } else if (read) verified.delete(key);

  return decorate(envelope.result, attested);
}
