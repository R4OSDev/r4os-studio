import { readFile, writeFile, rename, mkdir, rm, copyFile, lstat, mkdtemp, open } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { exec } from './systemd.js';
import { shareFiles, validFilename, createShareImage } from './share.js';
import { VmError } from './paths.js';

type Entry = { name: string; sha256: string; size: number };
type Manifest = Record<string, Entry>;
interface SyncState { schema: 1; baseline: Manifest; pending: boolean; session: string; lastSyncedAt?: string; error?: string }
const statePath = (directory: string) => join(directory, 'Exchange/state.json');
const imagePath = (directory: string) => join(directory, 'Disks/exchange.img');
const imageArg = (directory: string) => imagePath(directory) + '@@1048576';

export async function shareState(directory: string): Promise<SyncState | undefined> {
  let value: string;
  try { value = await readFile(statePath(directory), 'utf8'); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  const state = JSON.parse(value) as SyncState;
  if (state.schema !== 1 || typeof state.pending !== 'boolean' || !/^[a-f0-9-]{36}$/.test(state.session)
    || !state.baseline || typeof state.baseline !== 'object') throw new VmError('Invalid exchange sync state. Preserve the image and check Exchange/state.json.');
  for (const [key, entry] of Object.entries(state.baseline)) {
    if (!validFilename(entry.name) || key !== entry.name.toLowerCase() || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new VmError('Invalid exchange baseline.');
  }
  state.baseline = Object.assign(Object.create(null), state.baseline);
  return state;
}
async function save(directory: string, state: SyncState) {
  const temp = statePath(directory) + `.${randomUUID()}.tmp`;
  await writeFile(temp, JSON.stringify(state, null, 2) + '\n', { mode: 0o600, flush: true });
  await rename(temp, statePath(directory));
  const parent = await open(join(directory, 'Exchange'), 'r');
  try { await parent.sync(); } finally { await parent.close(); }
}
async function manifest(path: string): Promise<Manifest> {
  const result: Manifest = Object.create(null);
  for (const file of await shareFiles(path)) {
    const bytes = await readFile(join(path, file.name));
    result[file.name.toLowerCase()] = { ...file, sha256: createHash('sha256').update(bytes).digest('hex') };
  }
  return result;
}
const equal = (a?: Entry, b?: Entry) => a?.sha256 === b?.sha256;
const same = (a: Manifest, b: Manifest) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every((key) => equal(a[key], b[key]) && a[key].name === b[key]?.name);
function bounded(entries: Manifest) {
  if (Object.keys(entries).length > 128 || Object.values(entries).reduce((sum, entry) => sum + entry.size, 0) > 96 * 1024 * 1024) throw new VmError('The merged exchange exceeds 128 files or 96 MiB. The image has been preserved.');
}
async function extract(directory: string, target: string) {
  const info = await lstat(imagePath(directory));
  if (!info.isFile() || info.isSymbolicLink() || info.size !== 257 * 1024 * 1024) throw new VmError('Invalid exchange image.');
  const { stdout } = await exec('/usr/bin/mdir', ['-b', '-i', imageArg(directory), '::/'], { timeout: 30_000, maxBuffer: 64 * 1024 });
  const names = stdout.split(/\r?\n/).filter(Boolean).map((line) => {
    if (!line.startsWith('::/') || !validFilename(line.slice(3))) throw new VmError('Guest exchange contains unsupported names or folders. Preserve exchange.img and recover those files before restarting.');
    return line.slice(3);
  });
  if (names.length > 128 || new Set(names.map((n) => n.toLowerCase())).size !== names.length) throw new VmError('Guest exchange has too many files or conflicting filenames.');
  for (const name of names) await exec('/usr/bin/mcopy', ['-i', imageArg(directory), `::/${name}`, join(target, name)], { timeout: 30_000 });
  return manifest(target);
}

/** Runs only after QEMU has exited, or during stopped-VM recovery. Never mount a live image. */
export async function finishShare(directory: string) {
  const state = await shareState(directory);
  if (!state?.pending) return;
  const share = join(directory, 'Exchange/Share');
  const temp = await mkdtemp(join(directory, 'Exchange/.sync-'));
  try {
    const guest = await extract(directory, temp), host = await manifest(share);
    const merged: Manifest = { ...host };
    const changed = Object.keys({ ...state.baseline, ...guest }).filter((key) => !equal(state.baseline[key], guest[key]));
    const conflicts = changed.filter((key) => !equal(host[key], state.baseline[key]) && !equal(host[key], guest[key]));
    if (conflicts.length) {
      // Keep previous conflict attempts intact, including host edits made during resolution.
      state.session = randomUUID();
      const backup = join(directory, 'Exchange/Conflicts', state.session);
      await mkdir(join(backup, 'Guest'), { recursive: true, mode: 0o700 });
      await mkdir(join(backup, 'Host'), { recursive: true, mode: 0o700 });
      for (const key of conflicts) {
        if (guest[key]) await copyFile(join(temp, guest[key].name), join(backup, 'Guest', guest[key].name));
        if (host[key]) await copyFile(join(share, host[key].name), join(backup, 'Host', host[key].name));
      }
      await writeFile(join(backup, 'conflicts.json'), JSON.stringify({ conflicts, baseline: state.baseline, guest, host }, null, 2));
      throw new VmError(`Exchange conflict: ${conflicts.join(', ')}. Both versions are preserved in Exchange/Conflicts/${state.session}/. Resolve the host files, then retry exchange sync. Use the guest version or restore the last common version (remove the host file if it did not exist previously).`);
    }
    for (const key of changed) { if (guest[key]) merged[key] = guest[key]; else delete merged[key]; }
    bounded(merged);
    if (!same(host, await manifest(share))) throw new VmError('The host exchange changed during sync. Retry when host edits have finished.');
    // Per-file atomic publication is replayable: already applied changes equal the guest on recovery.
    for (const key of changed) {
      const old = host[key], entry = guest[key];
      if (entry) {
        const staged = join(directory, 'Exchange', `.publish-${randomUUID()}`);
        await copyFile(join(temp, entry.name), staged);
        const file = await open(staged, 'r');
        try { await file.sync(); } finally { await file.close(); }
        await rename(staged, join(share, old?.name ?? entry.name));
      } else if (old) await rm(join(share, old.name));
    }
    const folder = await open(share, 'r');
    try { await folder.sync(); } finally { await folder.close(); }
    await save(directory, { ...state, baseline: guest, pending: false, error: undefined, lastSyncedAt: new Date().toISOString() });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Exchange synchronization failed.';
    await save(directory, { ...state, error: message });
    throw error;
  } finally { await rm(temp, { recursive: true, force: true }); }
}

/** Import stopped-host edits without ever replacing an unexported guest image. */
export async function prepareShare(directory: string) {
  await finishShare(directory);
  let state = await shareState(directory);
  if (!state) {
    // Legacy read-only snapshots never contained guest changes; retain them until migration succeeds.
    const temp = await mkdtemp(join(directory, 'Exchange/.adopt-'));
    try {
      let baseline: Manifest = Object.create(null);
      try { await lstat(imagePath(directory)); baseline = await extract(directory, temp); }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
      state = { schema: 1, pending: false, baseline, session: randomUUID() };
      await save(directory, state);
    } finally { await rm(temp, { recursive: true, force: true }); }
  }
  const host = await manifest(join(directory, 'Exchange/Share'));
  let exists = true;
  try { const info = await lstat(imagePath(directory)); if (!info.isFile() || info.isSymbolicLink() || info.size !== 257 * 1024 * 1024) throw new VmError('Invalid exchange image.'); } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') exists = false; else throw error; }
  if (!exists || !same(host, state.baseline)) await createShareImage(directory);
  if (!same(host, await manifest(join(directory, 'Exchange/Share')))) throw new VmError('The host exchange changed during import. Stop editing and retry.');
  await save(directory, { ...state, baseline: host, session: randomUUID(), pending: true, error: undefined });
}
