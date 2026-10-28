import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink, open, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import Fastify from 'fastify';

const testRoot = await mkdtemp(join(tmpdir(), 'studio-vm-test-'));
const directory = join(testRoot, 'R4OS'); await mkdir(directory);
process.env.STUDIO_R4OS_DIR = directory;
process.env.STUDIO_VM_NETWORK_CAPABILITY = join(directory, 'network-capability.json');
const { vmRoutes } = await import('../src/modules/virtual-machines/routes.js');
const { createShareImage, hashShareFile } = await import('../src/modules/virtual-machines/share.js');
const { exchangeImageBytes, exchangeLimits } = await import('../src/modules/virtual-machines/exchange-policy.js');
const { prepareExchangeIdentity } = await import('../src/modules/virtual-machines/exchange-identity.js');
const { prepareShare, finishShare, shareState } = await import('../src/modules/virtual-machines/share-sync.js');
const { exec } = await import('../src/modules/virtual-machines/systemd.js');

await test('VM administration requires same-origin session/CSRF, preserves VM pins and uses the selected local default release', async () => {
  // Small raw fixtures test management only; real guest boots are separate checks.
  const base = Buffer.alloc(1024 * 1024);
  for (const version of ['0.9.9', '0.10.0']) {
    const id = `${version}-full`, path = join(directory, 'Images', id);
    await mkdir(path, { recursive: true }); await writeFile(join(path, 'disk.img'), base);
    await writeFile(join(path, 'image.json'), JSON.stringify({ schema: 1, id, version, variant: 'full', architecture: 'x86_64', disk: 'disk.img', sha256: createHash('sha256').update(base).digest('hex') }));
  }
  const app = Fastify(); app.register(vmRoutes, { prefix: '/api/vms' });
  try {
    const initial = await app.inject('/api/vms'); assert.equal(initial.statusCode, 200);
    const cookie = initial.cookies[0];
    const headers = { cookie: `${cookie.name}=${cookie.value}`, 'x-csrf-token': initial.json().csrfToken };
    const input = { name: 'A', cpus: 2, memoryMiB: 2048 };
    assert.equal((await app.inject({ method: 'POST', url: '/api/vms', payload: input })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/vms', headers: { ...headers, origin: 'https://foreign.example' }, payload: input })).statusCode, 403);
    const created = await app.inject({ method: 'POST', url: '/api/vms', headers, payload: { ...input, networkEnabled: false } });
    assert.equal(created.statusCode, 201); const vm = created.json().vm;
    assert.equal(vm.imageId, '0.10.0-full'); assert.equal(vm.state, 'stopped');
    assert.equal(vm.networkEnabled, false);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, networkEnabled: true } })).statusCode, 409);
    await writeFile(process.env.STUDIO_VM_NETWORK_CAPABILITY!, JSON.stringify({ schema: 1, mode: 'user', device: 'rtl8139' }));
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, networkEnabled: 'false' } })).statusCode, 400);
    const network = await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, networkEnabled: true } });
    assert.equal(network.statusCode, 200); assert.equal(network.json().vm.networkEnabled, true);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: input })).json().vm.networkEnabled, true);
    assert.equal(JSON.parse(await readFile(join(directory, 'Instances', vm.id, 'vm.json'), 'utf8')).networkEnabled, true);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, networkEnabled: false } })).json().vm.networkEnabled, false);

    await mkdir(join(directory, 'Profiles'), { recursive: true });
    await writeFile(join(directory, 'Profiles/versions.json'), JSON.stringify({ schema: 1, defaults: { r4os: { id: '0.9.9-full', sha256: createHash('sha256').update(base).digest('hex') } } }));
    assert.equal((await app.inject('/api/vms')).json().defaultImageId, '0.9.9-full');
    const second = await app.inject({ method: 'POST', url: '/api/vms', headers, payload: { ...input, name: 'Uses selected default' } });
    assert.equal(second.statusCode, 201); const secondVm = second.json().vm; assert.equal(secondVm.networkEnabled, true);
    assert.equal(secondVm.imageId, '0.9.9-full');
    assert.equal((await app.inject('/api/vms')).json().vms.find((item: { id: string }) => item.id === vm.id).imageId, '0.10.0-full');
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/vms/${secondVm.id}`, headers, payload: { confirm: true } })).statusCode, 204);
    await writeFile(join(directory, 'Profiles/versions.json'), JSON.stringify({ schema: 1, defaults: { r4os: { id: 'missing', sha256: 'a'.repeat(64) } } }));
    assert.equal((await app.inject('/api/vms')).json().defaultImageId, null);
    assert.equal((await app.inject({ method: 'POST', url: '/api/vms', headers, payload: input })).statusCode, 409);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/console-ticket` })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/console-ticket`, headers })).statusCode, 409);
    assert.equal((await app.inject({ method: 'GET', url: `/api/vms/${vm.id}/console`, headers: { ...headers, origin: 'https://foreign.example' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, cpus: 999 } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: '../escape.txt', content: 'YQ==' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: 'TEST.TXT', content: 'YQ==' } })).statusCode, 204);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: 'test.txt', content: 'Yg==' } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/vms/${vm.id}`, headers, payload: { confirm: false } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/vms/${vm.id}`, headers, payload: { confirm: true } })).statusCode, 204);
    assert.deepEqual(await readFile(join(directory, 'Images/0.10.0-full/disk.img')), base);
  } finally { await app.close(); }
});

await test('persistent FAT32 exchange exports guest edits, survives starts, detects conflicts and rejects unsafe entries', async (t) => {
  try { await exec('/usr/sbin/mkfs.fat', ['--help']); await exec('/usr/bin/mtype', ['-V']); }
  catch { t.skip('Host FAT tools are not installed.'); return; }
  const path = join(directory, randomUUID()); await mkdir(join(path, 'Exchange/Share'), { recursive: true });
  await writeFile(join(path, 'Exchange/Share/TEST.TXT'), 'VM private artifact');
  await prepareShare(path);
  const imageFile = await open(join(path, 'Disks/exchange.img'), 'r'), disk = Buffer.alloc(1048576 + 90);
  try { await imageFile.read(disk, 0, disk.length, 0); } finally { await imageFile.close(); }
  assert.equal((await stat(join(path, 'Disks/exchange.img'))).size, exchangeImageBytes);
  assert.equal(disk[450], 0x0c); assert.equal(disk.readUInt32LE(454), 2048);
  assert.equal(disk.subarray(1048576 + 82, 1048576 + 90).toString(), 'FAT32   ');
  const { stdout } = await exec('/usr/bin/mtype', ['-i', join(path, 'Disks/exchange.img') + '@@1048576', '::/TEST.TXT']);
  assert.equal(stdout, 'VM private artifact');
  const image = join(path, 'Disks/exchange.img') + '@@1048576';
  const guest = join(path, 'GUEST.TXT'); await writeFile(guest, 'guest output');
  await exec('/usr/bin/mcopy', ['-i', image, guest, '::/GUEST.TXT']);
  await exec('/usr/bin/mdel', ['-i', image, '::/TEST.TXT']);
  // Changes on different sides merge. Deletions are propagated too.
  await writeFile(join(path, 'Exchange/Share/HOST.TXT'), 'host addition');
  await finishShare(path);
  assert.equal(await readFile(join(path, 'Exchange/Share/GUEST.TXT'), 'utf8'), 'guest output');
  await assert.rejects(readFile(join(path, 'Exchange/Share/TEST.TXT')), { code: 'ENOENT' });
  assert.equal((await shareState(path))?.pending, false);
  await prepareShare(path);
  assert.equal((await exec('/usr/bin/mtype', ['-i', image, '::/GUEST.TXT'])).stdout, 'guest output');
  assert.equal((await exec('/usr/bin/mtype', ['-i', image, '::/HOST.TXT'])).stdout, 'host addition');
  await writeFile(guest, 'new guest version');
  await exec('/usr/bin/mcopy', ['-o', '-i', image, guest, '::/GUEST.TXT']);
  await writeFile(join(path, 'Exchange/Share/GUEST.TXT'), 'conflicting host version');
  await assert.rejects(finishShare(path), /Exchange conflict/);
  const conflict = await shareState(path);
  assert.equal(conflict?.pending, true);
  assert.equal(await readFile(join(path, 'Exchange/Conflicts', conflict!.session, 'Guest/GUEST.TXT'), 'utf8'), 'new guest version');
  assert.equal(await readFile(join(path, 'Exchange/Share/GUEST.TXT'), 'utf8'), 'conflicting host version');
  await assert.rejects(prepareShare(path), /Exchange conflict/);
  assert.notEqual((await shareState(path))?.session, conflict?.session);
  assert.equal(await readFile(join(path, 'Exchange/Conflicts', conflict!.session, 'Host/GUEST.TXT'), 'utf8'), 'conflicting host version');
  // Choose the guest copy explicitly, then recover.
  await writeFile(join(path, 'Exchange/Share/GUEST.TXT'), 'new guest version');
  await finishShare(path); await prepareShare(path); await finishShare(path);
  assert.equal(await readFile(join(path, 'Exchange/Share/GUEST.TXT'), 'utf8'), 'new guest version');
  await symlink('/etc/passwd', join(path, 'Exchange/Share/LINK.TXT'));
  await assert.rejects(prepareShare(path), /links and special files are rejected/);
});
await test('empty exchange can start and stop; interrupted export is recovered before import', async () => {
  const path = join(directory, randomUUID()); await mkdir(join(path, 'Exchange/Share'), { recursive: true });
  await prepareShare(path); await finishShare(path);
  await prepareShare(path);
  const content = join(path, 'RECOVER.TXT'); await writeFile(content, 'recover before next boot');
  await exec('/usr/bin/mcopy', ['-i', join(path, 'Disks/exchange.img') + '@@1048576', content, '::/RECOVER.TXT']);
  // No stop callback: the next start must export first instead of overwriting the image.
  await prepareShare(path);
  assert.equal(await readFile(join(path, 'Exchange/Share/RECOVER.TXT'), 'utf8'), 'recover before next boot');
  await finishShare(path);
  const legacy = join(directory, randomUUID()); await mkdir(join(legacy, 'Exchange/Share'), { recursive: true });
  await writeFile(join(legacy, 'Exchange/Share/OLD.TXT'), 'old snapshot'); await createShareImage(legacy);
  await writeFile(join(legacy, 'Exchange/Share/OLD.TXT'), 'edited while stopped');
  await prepareShare(legacy); await finishShare(legacy);
  assert.equal(await readFile(join(legacy, 'Exchange/Share/OLD.TXT'), 'utf8'), 'edited while stopped');
  // Unsupported guest directories must block export/import without touching the image or host files.
  await prepareShare(legacy);
  const legacyImage = join(legacy, 'Disks/exchange.img');
  await exec('/usr/bin/mmd', ['-i', legacyImage + '@@1048576', '::/SUBDIR']);
  await assert.rejects(finishShare(legacy), /Unsupported guest Exchange path/);
  await assert.rejects(prepareShare(legacy), /Unsupported guest Exchange path/);
  assert.equal(await readFile(join(legacy, 'Exchange/Share/OLD.TXT'), 'utf8'), 'edited while stopped');
  assert.equal((await shareState(legacy))?.pending, true);
});
await test('larger exchange preserves pending legacy guest edits and hashes a full-quota file in chunks', async () => {
  const path = join(directory, randomUUID()), share = join(path, 'Exchange/Share');
  await mkdir(share, { recursive: true }); await mkdir(join(path, 'Disks'));
  await writeFile(join(share, 'OLD.TXT'), 'old baseline'); await prepareExchangeIdentity(path);
  const baseline = Object.create(null);
  for (const name of ['OLD.TXT', 'STXCHG.JSN']) {
    const data = await readFile(join(share, name));
    baseline[name.toLowerCase()] = { name, kind: 'file', size: data.length, sha256: createHash('sha256').update(data).digest('hex') };
  }
  await writeFile(join(path, 'Exchange/state.json'), JSON.stringify({ schema: 2, pending: true, session: randomUUID(), baseline }));
  const image = join(path, 'Disks/exchange.img'), legacy = await open(image, 'wx');
  try {
    await legacy.truncate(257 * 1024 * 1024);
    const mbr = Buffer.alloc(512); mbr[450] = 0x0c; mbr.writeUInt32LE(2048, 454);
    mbr.writeUInt32LE(256 * 1024 * 1024 / 512, 458); mbr[510] = 0x55; mbr[511] = 0xaa;
    await legacy.write(mbr, 0, mbr.length, 0);
  } finally { await legacy.close(); }
  await exec('/usr/sbin/mkfs.fat', ['-F', '32', '-n', 'R4SHARE', '--offset=2048', image]);
  for (const name of ['OLD.TXT', 'STXCHG.JSN']) await exec('/usr/bin/mcopy', ['-i', image + '@@1048576', join(share, name), '::/' + name]);
  const guest = join(path, 'guest'); await writeFile(guest, 'pending guest edit');
  await exec('/usr/bin/mcopy', ['-o', '-i', image + '@@1048576', guest, '::/OLD.TXT']);
  await writeFile(join(share, 'HOST.TXT'), 'independent host edit');
  await prepareShare(path);
  assert.equal((await stat(image)).size, exchangeImageBytes);
  for (const [name, expected] of [['OLD.TXT', 'pending guest edit'], ['HOST.TXT', 'independent host edit']]) {
    assert.equal(await readFile(join(share, name), 'utf8'), expected);
    assert.equal((await exec('/usr/bin/mtype', ['-i', image + '@@1048576', '::/' + name])).stdout, expected);
  }
  assert.equal(createHash('sha256').update(await readFile(join(share, 'STXCHG.JSN'))).digest('hex'), baseline['stxchg.jsn'].sha256);
  await finishShare(path);
  // Sparse input exercises the actual 1 GiB reader without allocating a giant
  // test buffer or repeatedly copying gigabytes through a guest VM.
  const large = await open(join(share, 'LARGE.BIN'), 'wx');
  try { await large.truncate(exchangeLimits.bytes); } finally { await large.close(); }
  const hash = createHash('sha256'), chunk = Buffer.alloc(1024 * 1024);
  for (let size = 0; size < exchangeLimits.bytes; size += chunk.length) hash.update(chunk);
  assert.equal(await hashShareFile(share, { name: 'LARGE.BIN', size: exchangeLimits.bytes, kind: 'file' }, Date.now() + 30_000), hash.digest('hex'));
});
await rm(testRoot, { recursive: true, force: true });
