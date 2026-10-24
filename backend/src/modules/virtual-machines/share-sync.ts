import { readFile, writeFile, rename, mkdir, rm, lstat, mkdtemp, open } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { exec } from './systemd.js';
import { shareFiles, validSharePath, createShareImage, boundShare, readShareFile, exchangeLimits, type ShareEntry } from './share.js';
import { prepareExchangeIdentity, verifyExchangeMarker } from './exchange-identity.js';
import { VmError } from './paths.js';

type Entry = ShareEntry & { sha256: string };
type Manifest = Record<string, Entry>;
interface SyncState { schema: 1 | 2; baseline: Manifest; pending: boolean; session: string; lastSyncedAt?: string; error?: string }
interface Merge { schema: 1; id: string; before: string; after: string; state: SyncState }
const statePath = (directory: string) => join(directory, 'Exchange/state.json');
const imagePath = (directory: string) => join(directory, 'Disks/exchange.img');
const inode = async (path: string) => { const stat = await lstat(path); if (!stat.isDirectory() || stat.isSymbolicLink()) throw new VmError('Invalid Exchange transaction folder.'); return stat.dev + ':' + stat.ino; };
async function sync(path: string) { const file = await open(path, 'r'); try { await file.sync(); } finally { await file.close(); } }
async function json(path: string, value: unknown) {
  const temp = path + '.' + randomUUID() + '.tmp';
  await writeFile(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx', flush: true });
  await rename(temp, path); await sync(dirname(path));
}
function validate(entries: Manifest) {
  if (!entries || typeof entries !== 'object' || Array.isArray(entries)) throw new VmError('Invalid Exchange baseline.');
  for (const [key, entry] of Object.entries(entries)) {
    entry.kind ??= 'file';
    if (!['file', 'directory'].includes(entry.kind) || !validSharePath(entry.name, entry.kind === 'directory') || key !== entry.name.toLowerCase()
      || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new VmError('Invalid Exchange baseline.');
  }
  boundShare(Object.values(entries));
}
export async function shareState(directory: string): Promise<SyncState | undefined> {
  let value: string;
  try { value = await readFile(statePath(directory), 'utf8'); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  const state = JSON.parse(value) as SyncState;
  if (![1, 2].includes(state.schema) || typeof state.pending !== 'boolean' || !/^[a-f0-9-]{36}$/.test(state.session))
    throw new VmError('Unsupported Exchange sync state. Preserve the image and use a compatible Studio release.');
  validate(state.baseline); state.baseline = Object.assign(Object.create(null), state.baseline); return state;
}
async function save(directory: string, state: SyncState) { await json(statePath(directory), { ...state, schema: 2 }); }
async function manifest(path: string): Promise<Manifest> {
  const result: Manifest = Object.create(null);
  for (const entry of await shareFiles(path)) result[entry.name.toLowerCase()] = { ...entry,
    sha256: createHash('sha256').update(entry.kind === 'directory' ? 'directory' : await readShareFile(path, entry)).digest('hex') };
  return result;
}
const equal = (a?: Entry, b?: Entry) => a?.sha256 === b?.sha256 && a?.kind === b?.kind && a?.name === b?.name;
const same = (a: Manifest, b: Manifest) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every((key) => equal(a[key], b[key]));
async function extract(directory: string, target: string) {
  const info = await lstat(imagePath(directory));
  if (!info.isFile() || info.isSymbolicLink() || info.size !== 257 * 1024 * 1024) throw new VmError('Invalid Exchange image.');
  const deadline = Date.now() + exchangeLimits.seconds * 1000, entries: ShareEntry[] = [];
  const run = (command: string, args: string[]) => {
    const timeout = Math.min(30_000, deadline - Date.now()); if (timeout <= 0) throw new VmError('Exchange export exceeded its deadline.');
    return exec(command, args, { timeout, maxBuffer: 64 * 1024 });
  };
  async function scan(parent = '') {
    const { stdout } = await run('/usr/bin/mdir', ['-a', '-b', '-i', imagePath(directory) + '@@1048576', '::/' + (parent ? parent + '/' : '')]);
    const lines = stdout.split(/\r?\n/).filter(Boolean);
    if (lines.length > exchangeLimits.files + exchangeLimits.directories) throw new VmError('Too many guest Exchange entries.');
    for (const line of lines) {
      const isDir = line.endsWith('/'), name = line.slice(3, isDir ? -1 : undefined);
      if (name === (parent ? parent + '/.' : '.') || name === (parent ? parent + '/..' : '..')) continue;
      if (!line.startsWith('::/') || !validSharePath(name, isDir) || dirname(name) !== (parent || '.'))
        throw new VmError('Unsupported guest Exchange path. Preserve exchange.img and recover the files before restarting.');
      if (entries.some((e) => e.name.toLowerCase() === name.toLowerCase())) throw new VmError('Guest Exchange paths conflict ignoring case.');
      const entry: ShareEntry = { name, size: 0, kind: isDir ? 'directory' : 'file' }; entries.push(entry);
      if (entries.length > exchangeLimits.files + exchangeLimits.directories) throw new VmError('Too many guest Exchange entries.');
      if (isDir) { boundShare(entries); await mkdir(join(target, name), { mode: 0o700 }); await scan(name); }
      else {
        const remaining = exchangeLimits.bytes - entries.reduce((sum, e) => sum + e.size, 0);
        await run('/usr/bin/python3', [fileURLToPath(new URL('../../../../scripts/exchange-copy.py', import.meta.url)),
          String(remaining), imagePath(directory) + '@@1048576', '::/' + name, join(target, name)]);
        entry.size = (await lstat(join(target, name))).size; boundShare(entries);
      }
    }
  }
  await scan(); return manifest(target);
}
async function copyTree(target: string, entries: Manifest, source: (key: string) => string) {
  await mkdir(target, { mode: 0o700 }); const deadline = Date.now() + exchangeLimits.seconds * 1000;
  const ordered = Object.entries(entries).sort((a, b) => a[1].name.split('/').length - b[1].name.split('/').length);
  for (const [key, entry] of ordered) {
    if (Date.now() > deadline) throw new VmError('Exchange copy exceeded its deadline.');
    if (entry.kind === 'directory') await mkdir(join(target, entry.name), { mode: 0o700 });
    else {
      const data = await readShareFile(source(key), entry);
      if (createHash('sha256').update(data).digest('hex') !== entry.sha256) throw new VmError('Exchange source changed during publication.');
      await writeFile(join(target, entry.name), data, { mode: 0o600, flag: 'wx', flush: true });
    }
  }
  for (const [, entry] of ordered.reverse()) if (entry.kind === 'directory') await sync(join(target, entry.name));
  await sync(target);
}
/** Recover by inode identity: never exchange twice after an uncertain publication. */
async function recoverMerge(directory: string) {
  const path = join(directory, 'Exchange/merge.json'); let value: Merge;
  try { value = JSON.parse(await readFile(path, 'utf8')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  if (value.schema !== 1 || !/^[a-f0-9-]{36}$/.test(value.id) || !/^\d+:\d+$/.test(value.before) || !/^\d+:\d+$/.test(value.after)) throw new VmError('Invalid Exchange merge journal.');
  validate(value.state.baseline);
  const current = await inode(join(directory, 'Exchange/Share')), stage = join(directory, 'Exchange/.merge-' + value.id);
  if (current === value.after) await save(directory, value.state);
  else if (current !== value.before) throw new VmError('Exchange publication identity changed. Preserve all transaction folders.');
  try {
    if (await inode(stage) !== (current === value.after ? value.before : value.after)) throw new VmError('Exchange staging identity changed.');
    await rm(stage, { recursive: true });
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  await rm(path); await sync(join(directory, 'Exchange'));
}
/** Only after QEMU exits. A whole-tree atomic swap handles parent/type changes and is replay-safe. */
export async function finishShare(directory: string) {
  await recoverMerge(directory);
  const state = await shareState(directory); if (!state?.pending) return;
  const share = join(directory, 'Exchange/Share'), temp = await mkdtemp(join(directory, 'Exchange/.sync-'));
  let stage: string | undefined, journaled = false;
  try {
    const guest = await extract(directory, temp), host = await manifest(share);
    await verifyExchangeMarker(directory, temp); await verifyExchangeMarker(directory, share);
    const merged: Manifest = { ...host };
    const changed = Object.keys({ ...state.baseline, ...guest }).filter((key) => !equal(state.baseline[key], guest[key]));
    const conflicts = changed.filter((key) => !equal(host[key], state.baseline[key]) && !equal(host[key], guest[key]));
    for (const key of changed) { if (guest[key]) merged[key] = guest[key]; else delete merged[key]; }
    let structural = false; try { validate(merged); } catch { structural = true; }
    if (conflicts.length || structural) {
      state.session = randomUUID(); const backup = join(directory, 'Exchange/Conflicts', state.session);
      await mkdir(backup, { recursive: true, mode: 0o700 });
      await copyTree(join(backup, 'Guest'), guest, () => temp); await copyTree(join(backup, 'Host'), host, () => share);
      await json(join(backup, 'conflicts.json'), { conflicts, structural, baseline: state.baseline, guest, host });
      throw new VmError(`Exchange conflict. Both trees are preserved in Exchange/Conflicts/${state.session}/. Resolve host files against the baseline or guest version, then retry exchange sync.`);
    }
    const id = randomUUID(); stage = join(directory, 'Exchange/.merge-' + id);
    await copyTree(stage, merged, (key) => changed.includes(key) ? temp : share);
    if (!same(merged, await manifest(stage)) || !same(host, await manifest(share))) throw new VmError('Exchange changed during sync. Retry when host edits have finished.');
    const result = { ...state, baseline: guest, pending: false, error: undefined, lastSyncedAt: new Date().toISOString() };
    await json(join(directory, 'Exchange/merge.json'), { schema: 1, id, before: await inode(share), after: await inode(stage), state: result }); journaled = true;
    await exec('/usr/bin/python3', [fileURLToPath(new URL('../../../../scripts/exchange-swap.py', import.meta.url)), join(directory, 'Exchange'), id], { timeout: 30_000 });
    await recoverMerge(directory);
  } catch (error) {
    // A published tree is identified and finalized on the next recovery. Never replay the swap.
    if (!journaled) await save(directory, { ...state, error: error instanceof Error ? error.message : 'Exchange synchronization failed.' });
    throw error;
  } finally { await rm(temp, { recursive: true, force: true }); if (stage && !journaled) await rm(stage, { recursive: true, force: true }); }
}
export async function prepareShare(directory: string) {
  await finishShare(directory); let state = await shareState(directory);
  if (!state) {
    const temp = await mkdtemp(join(directory, 'Exchange/.adopt-'));
    try {
      let baseline: Manifest = Object.create(null);
      try { await lstat(imagePath(directory)); baseline = await extract(directory, temp); }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
      state = { schema: 2, pending: false, baseline, session: randomUUID() }; await save(directory, state);
    } finally { await rm(temp, { recursive: true, force: true }); }
  }
  await prepareExchangeIdentity(directory);
  const host = await manifest(join(directory, 'Exchange/Share')); let exists = true;
  try { const info = await lstat(imagePath(directory)); if (!info.isFile() || info.isSymbolicLink() || info.size !== 257 * 1024 * 1024) throw new VmError('Invalid Exchange image.'); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') exists = false; else throw error; }
  if (!exists || !same(host, state.baseline)) await createShareImage(directory);
  if (!same(host, await manifest(join(directory, 'Exchange/Share')))) throw new VmError('Host Exchange changed during import. Stop editing and retry.');
  await save(directory, { ...state, baseline: host, session: randomUUID(), pending: true, error: undefined });
}
