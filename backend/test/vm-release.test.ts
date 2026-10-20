import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, stat, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import Fastify from 'fastify';

await test('confirmed VM release changes preserve exchange, reject stale/corrupt choices, retry safely and recover either side of directory exchange', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-release-test-'));
  process.env.STUDIO_R4OS_DIR = root;
  process.env.STUDIO_VM_NETWORK_CAPABILITY = join(root, 'network.json');
  const { vmRoutes } = await import('../src/modules/virtual-machines/routes.js');
  const { VmManager } = await import('../src/modules/virtual-machines/service.js');
  const { prepareShare, finishShare } = await import('../src/modules/virtual-machines/share-sync.js');
  const { exec } = await import('../src/modules/virtual-machines/systemd.js');
  const app = Fastify(); app.register(vmRoutes, { prefix: '/api/vms' });
  const digest = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');
  try {
    await writeFile(process.env.STUDIO_VM_NETWORK_CAPABILITY, JSON.stringify({ schema: 1, mode: 'user' }));
    const records = [];
    for (const [version, fill] of [['1.0.0', 17], ['2.0.0', 34]] as const) {
      const id = version + '-full', path = join(root, 'Images', id), disk = Buffer.alloc(1024 * 1024, fill);
      await mkdir(path, { recursive: true }); await writeFile(join(path, 'disk.img'), disk);
      const image = { schema: 1, id, version, variant: 'full', architecture: 'x86_64', disk: 'disk.img', sha256: digest(disk) };
      await writeFile(join(path, 'image.json'), JSON.stringify(image)); records.push(image);
    }
    const initial = await app.inject('/api/vms'), cookie = initial.cookies[0];
    const headers = { cookie: `${cookie.name}=${cookie.value}`, 'x-csrf-token': initial.json().csrfToken };
    const input = { name: 'Release QA', cpus: 2, memoryMiB: 2048, networkEnabled: true };
    const created = await app.inject({ method: 'POST', url: '/api/vms', headers, payload: input });
    assert.equal(created.statusCode, 201); let vm = created.json().vm;
    const path = join(root, 'Instances', vm.id), disk = join(path, 'Disks/disk.qcow2');
    await writeFile(join(path, 'Exchange/Share/KEEP.TXT'), 'host and guest exchange');
    await prepareShare(path); await finishShare(path);
    await mkdir(join(path, 'Exchange/Conflicts/retained'), { recursive: true });
    await writeFile(join(path, 'Exchange/Conflicts/retained/KEEP.TXT'), 'retained conflict');
    const keep = ['Disks/exchange.img', 'Exchange/Share/KEEP.TXT', 'Exchange/state.json', 'Exchange/Conflicts/retained/KEEP.TXT'];
    const saved = await Promise.all(keep.map(async file => ({ file, inode: (await stat(join(path, file))).ino, hash: digest(await readFile(join(path, file))) })));
    // Emulate a guest write in the old private system overlay.
    await exec('/usr/bin/qemu-io', ['-f', 'qcow2', '-c', 'write -P 0x5a 0 512', disk]);
    const oldHash = digest(await readFile(disk));
    const target = records[0];
    const choice = { confirm: true, expectedRevision: vm.revision, expectedImageId: vm.imageId, expectedImageSha256: vm.imageSha256, imageId: target.id, imageSha256: target.sha256 };
    const change = (payload: unknown, selectedHeaders = headers) => app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}/release`, headers: selectedHeaders, payload });
    assert.equal((await change(choice, {} as typeof headers)).statusCode, 403);
    assert.equal((await change({ ...choice, confirm: false })).statusCode, 400);
    assert.equal((await change({ ...choice, expectedRevision: randomUUID() })).statusCode, 409);
    await writeFile(join(root, 'Images', target.id, 'disk.img'), Buffer.alloc(1024 * 1024, 99));
    assert.equal((await change(choice)).statusCode, 409);
    assert.equal(digest(await readFile(disk)), oldHash);
    await writeFile(join(root, 'Images', target.id, 'disk.img'), Buffer.alloc(1024 * 1024, 17));
    const switched = await change(choice); assert.equal(switched.statusCode, 200, switched.body); const before = vm; vm = switched.json().vm;
    assert.equal(vm.imageId, target.id); assert.notEqual(vm.revision, before.revision);
    for (const key of ['id', 'name', 'cpus', 'memoryMiB', 'networkEnabled', 'createdAt']) assert.equal(vm[key], before[key]);
    for (const file of saved) { assert.equal((await stat(join(path, file.file))).ino, file.inode); assert.equal(digest(await readFile(join(path, file.file))), file.hash); }
    const backing = async () => JSON.parse((await exec('/usr/bin/qemu-img', ['info', '--output=json', disk])).stdout)['backing-filename'];
    assert.equal(await backing(), join(root, 'Images', target.id, 'disk.img'));
    await exec('/usr/bin/qemu-io', ['-f', 'qcow2', '-c', 'write -P 0x6b 0 512', disk]);
    const newHash = digest(await readFile(disk));
    assert.equal((await change(choice)).statusCode, 200); assert.equal(digest(await readFile(disk)), newHash);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/vms/${vm.id}`, headers, payload: { ...input, imageId: before.imageId } })).statusCode, 200);
    assert.equal(digest(await readFile(disk)), newHash); assert.equal(await backing(), join(root, 'Images', target.id, 'disk.img'));
    // Prepared but uncommitted transaction: startup keeps the current system disk.
    let config = JSON.parse(await readFile(join(path, 'vm.json'), 'utf8'));
    const operation = randomUUID(), nextRevision = randomUUID(), stage = join(root, 'Instances', `.release-${vm.id}-${operation}`), journal = join(root, 'Instances', `.release-${vm.id}.json`);
    const pending = { schema: 1, operation, previousRevision: config.revision, nextRevision };
    await mkdir(stage); await writeFile(journal, JSON.stringify(pending));
    await new VmManager().config(vm.id); assert.equal(digest(await readFile(disk)), newHash); await assert.rejects(stat(stage), { code: 'ENOENT' });
    // Simulated crash after the atomic exchange: startup completes cleanup and
    // retains the complete new config/disk pair.
    await cp(path, stage, { recursive: true }); await rm(join(stage, 'Disks/disk.qcow2'));
    const second = records[1];
    await exec('/usr/bin/qemu-img', ['create', '-f', 'qcow2', '-F', 'raw', '-b', join(root, 'Images', second.id, 'disk.img'), join(stage, 'Disks/disk.qcow2')]);
    config = { ...config, revision: nextRevision, imageId: second.id, imageSha256: second.sha256 };
    await writeFile(join(stage, 'vm.json'), JSON.stringify(config)); await writeFile(journal, JSON.stringify(pending));
    await exec('/usr/bin/python3', [join(process.cwd(), 'scripts/vm-release-swap.py'), join(root, 'Instances'), vm.id, operation]);
    const recovered = await new VmManager().config(vm.id); assert.equal(recovered.revision, nextRevision); assert.equal(await backing(), join(root, 'Images', second.id, 'disk.img'));
    await assert.rejects(stat(stage), { code: 'ENOENT' }); await assert.rejects(stat(journal), { code: 'ENOENT' });
    const recoveredHash = digest(await readFile(disk));
    assert.equal((await change(choice)).statusCode, 409); assert.equal(digest(await readFile(disk)), recoveredHash);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
