import { readFile, mkdir, rm, open, access, appendFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { vmPath, runtimePath, root } from './paths.js';
import { prepareShare } from './share.js';
import type { VmConfig, VmImage } from '../../../../shared/virtual-machines.js';

// Launched only by the fixed, unprivileged systemd VM template.
const id = process.argv[2];
const directory = vmPath(id);
async function run() {
  const config: VmConfig = JSON.parse(await readFile(join(directory, 'vm.json'), 'utf8'));
  if (config.id !== id || !/^[a-zA-Z0-9_.-]{1,100}$/.test(config.imageId)
    || !Number.isInteger(config.cpus) || config.cpus < 1 || config.cpus > 8
    || !Number.isInteger(config.memoryMiB) || config.memoryMiB < 2048 || config.memoryMiB > 16384) throw new Error('Invalid VM configuration.');
  const image: VmImage = JSON.parse(await readFile(join(root, 'Images', config.imageId, 'image.json'), 'utf8'));
  if (image.sha256 !== config.imageSha256) throw new Error('The base image identity changed.');
  await mkdir(runtimePath(id), { recursive: true, mode: 0o700 });
  await rm(join(runtimePath(id), 'qmp.sock'), { force: true });
  await prepareShare(directory);
  let kvm = false;
  try { await access('/dev/kvm', constants.R_OK | constants.W_OK); kvm = true; } catch { /* use TCG */ }
  const log = await open(join(directory, 'Logs/qemu.log'), 'w', 0o600);
  const args = ['-name', `R4OS Studio ${id}`, '-machine', `q35,accel=${kvm ? 'kvm' : 'tcg'}`,
    '-cpu', kvm ? 'host' : 'max', '-m', String(config.memoryMiB), '-smp', String(config.cpus),
    '-boot', 'c', '-display', 'none', '-vga', 'std', '-nic', 'none', '-monitor', 'none',
    '-drive', 'file=Disks/disk.qcow2,if=none,id=system,format=qcow2,cache=none',
    '-device', 'ich9-ahci,id=ahci0', '-device', 'ide-hd,drive=system,bus=ahci0.0,bootindex=1',
    '-drive', 'file=Disks/exchange.img,if=none,id=exchange,format=raw,readonly=on',
    '-device', 'qemu-xhci,id=exchange-usb', '-device', 'usb-storage,drive=exchange,bus=exchange-usb.0,removable=on',
    '-audiodev', 'driver=none,id=silent', '-device', 'ich9-intel-hda', '-device', 'hda-duplex,audiodev=silent',
    '-serial', 'file:Logs/serial.log', '-qmp', `unix:${join(runtimePath(id), 'qmp.sock')},server=on,wait=off`];
  const child = spawn('/usr/bin/qemu-system-x86_64', args, { cwd: directory, stdio: ['ignore', log.fd, log.fd] });
  process.on('SIGTERM', () => child.kill('SIGTERM'));
  process.on('SIGINT', () => child.kill('SIGTERM'));
  child.on('error', (error) => { console.error(error); process.exitCode = 1; });
  child.on('exit', (code) => { void log.close(); process.exitCode = code ?? 0; });

}
void run().catch(async (error: unknown) => {
  const message = error instanceof Error ? error.message : 'VM startup failed.';
  console.error(message);
  await appendFile(join(directory, 'Logs/qemu.log'), message + '\n').catch(() => {});
  process.exitCode = 1;
});
