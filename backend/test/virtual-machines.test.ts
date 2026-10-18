import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import Fastify from 'fastify';

const directory = await mkdtemp(join(tmpdir(), 'studio-vm-test-'));
process.env.STUDIO_R4OS_DIR = directory;
const { vmRoutes } = await import('../src/modules/virtual-machines/routes.js');
const { prepareShare } = await import('../src/modules/virtual-machines/share.js');
const { exec } = await import('../src/modules/virtual-machines/systemd.js');

await test('VM administration requires same-origin session/CSRF, preserves base images and chooses latest local release', async () => {
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
    const created = await app.inject({ method: 'POST', url: '/api/vms', headers, payload: input });
    assert.equal(created.statusCode, 201); const vm = created.json().vm;
    assert.equal(vm.imageId, '0.10.0-full'); assert.equal(vm.state, 'stopped');
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, cpus: 999 } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: '../escape.txt', content: 'YQ==' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: 'TEST.TXT', content: 'YQ==' } })).statusCode, 204);
    assert.equal((await app.inject({ method: 'POST', url: `/api/vms/${vm.id}/files`, headers, payload: { name: 'test.txt', content: 'Yg==' } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/vms/${vm.id}`, headers, payload: { confirm: false } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/vms/${vm.id}`, headers, payload: { confirm: true } })).statusCode, 204);
    assert.deepEqual(await readFile(join(directory, 'Images/0.10.0-full/disk.img')), base);
  } finally { await app.close(); }
});

await test('exchange snapshot is real partitioned FAT32 and excludes symlinks', async (t) => {
  try { await exec('/usr/sbin/mkfs.fat', ['--help']); await exec('/usr/bin/mtype', ['-V']); }
  catch { t.skip('Host FAT tools are not installed.'); return; }
  const path = join(directory, 'share-test'); await mkdir(join(path, 'Exchange/Share'), { recursive: true });
  await writeFile(join(path, 'Exchange/Share/TEST.TXT'), 'VM private artifact');
  await prepareShare(path);
  const disk = await readFile(join(path, 'Disks/exchange.img'));
  assert.equal(disk[450], 0x0c); assert.equal(disk.readUInt32LE(454), 2048);
  assert.equal(disk.subarray(1048576 + 82, 1048576 + 90).toString(), 'FAT32   ');
  const { stdout } = await exec('/usr/bin/mtype', ['-i', join(path, 'Disks/exchange.img') + '@@1048576', '::/TEST.TXT']);
  assert.equal(stdout, 'VM private artifact');
  await symlink('/etc/passwd', join(path, 'Exchange/Share/LINK.TXT'));
  await assert.rejects(prepareShare(path), /plain files/);
});
await rm(directory, { recursive: true, force: true });
