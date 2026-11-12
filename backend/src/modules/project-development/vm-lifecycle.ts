import { readFile } from 'node:fs/promises';
import type { VirtualMachine } from '../../../../shared/virtual-machines.js';
import type { VmManager } from '../virtual-machines/service.js';
import { VmError } from '../virtual-machines/paths.js';
import { exec } from '../virtual-machines/systemd.js';
import { join } from 'node:path';
import { projectsDirectory } from '../projects/store.js';

interface UnitProof { state: string; mainPid: string; controlPid: string; invocationId: string; cgroup: string }
interface ProcessProof { pid: number; birth: string }
export interface LifecycleProof {
  kind: 'vm_stop' | 'vm_restart'; phase: string; accessRevision?: number; shutdownIntentAt?: string; hardReset?: boolean;
  original?: { unit: UnitProof; process: ProcessProof; bootId: string };
  stopped?: { confirmed: boolean };
}

async function unit(id: string): Promise<UnitProof> {
  const { stdout } = await exec('/usr/bin/systemctl', ['show', `r4os-studio-vm@${id}.service`, '--property=ActiveState,MainPID,ControlPID,InvocationID,ControlGroup'], { timeout: 5000 });
  const value = Object.fromEntries(stdout.trim().split('\n').map(line => line.split('=')));
  if (!['active', 'activating', 'deactivating', 'inactive', 'failed', 'reloading'].includes(value.ActiveState)
    || !/^\d{1,10}$/.test(value.MainPID) || !/^\d{1,10}$/.test(value.ControlPID)
    || !/^(?:[a-f0-9]{32})?$/.test(value.InvocationID ?? '') || typeof value.ControlGroup !== 'string')
    throw new VmError('The original VM process/service identity could not be verified.', 503);
  return { state: value.ActiveState, mainPid: value.MainPID, controlPid: value.ControlPID, invocationId: value.InvocationID, cgroup: value.ControlGroup };
}
async function birth(pid: number): Promise<string | null> {
  if (!Number.isSafeInteger(pid) || pid <= 0 || pid > 2 ** 31) throw new VmError('Invalid original VM process identity.', 503);
  try {
    const value = (await readFile(`/proc/${pid}/stat`, 'utf8')).split(') ').at(-1)!.trim().split(/\s+/)[19];
    if (!/^\d+$/.test(value ?? '')) throw new VmError('The original VM process identity is unreadable.', 503);
    return value;
  }
  catch (cause) { if ((cause as NodeJS.ErrnoException).code === 'ENOENT') return null; throw new VmError('The original VM process end could not be checked.', 503); }
}
async function emptyGroup(group: string) {
  if (!group) return true;
  if (!group.startsWith('/') || group.length > 1024 || group.includes('\0') || group.split('/').some(part => ['.', '..'].includes(part)))
    throw new VmError('Invalid original VM process group.', 503);
  try { return !(await readFile('/sys/fs/cgroup' + group + '/cgroup.procs', 'utf8')).trim(); }
  catch (cause) { if ((cause as NodeJS.ErrnoException).code === 'ENOENT') return true; throw new VmError('The original VM process group end could not be checked.', 503); }
}
export async function lifecycleInfo(manager: VmManager, id: string, proof: LifecycleProof) {
  const observed = await unit(id), vm = await manager.get(id), original = proof.original;
  if (original && observed.invocationId && observed.invocationId !== original.unit.invocationId
    && !['restart_intent', 'waiting_for_vm', 'waiting_for_ssh', 'ready'].includes(proof.phase))
    throw new VmError('The original VM boot was replaced. No further power action is authorized.');
  const pid = Number(observed.mainPid), currentBirth = pid ? await birth(pid) : null;
  const process = pid && currentBirth ? { pid, birth: currentBirth } : null;
  const originalProcessAlive = !!original?.process && await birth(original.process.pid) === original.process.birth;
  const fullyStopped = ['inactive', 'failed'].includes(observed.state) && observed.mainPid === '0' && observed.controlPid === '0'
    && ['stopped', 'failed'].includes(vm.state) && await emptyGroup(original?.unit.cgroup || observed.cgroup);
  const sync = vm.shareSync, synchronized = !!sync && !sync.pending && !sync.error
    && typeof sync.lastSyncedAt === 'string' && Number.isFinite(Date.parse(sync.lastSyncedAt));
  const exportComplete = (synchronized || !sync && !observed.invocationId && !original)
    && (!proof.shutdownIntentAt || !!sync?.lastSyncedAt && Date.parse(sync.lastSyncedAt) >= Date.parse(proof.shutdownIntentAt));
  return { vm, unit: observed, process, fullyStopped, exportComplete, originalProcessAlive };
}
export async function lifecycleEffect(manager: VmManager, id: string, proof: LifecycleProof, action: 'shutdown' | 'start' | 'restart') {
  const info = await lifecycleInfo(manager, id, proof), original = proof.original;
  if (!original) throw new VmError('The original lifecycle run has no bound VM generation.');
  if (action === 'shutdown' || action === 'restart') {
    const hard = action === 'restart';
    const effect = hard ? 'hard restart' : 'shutdown';
    if ((hard && (proof.kind !== 'vm_restart' || proof.hardReset !== true))
      || proof.phase !== (hard ? 'reset_intent' : 'shutdown_intent')
      || !(info.vm.state === 'running' || (hard && info.vm.state === 'paused')) || info.unit.controlPid !== '0'
      || info.unit.invocationId !== original.unit.invocationId || info.process?.pid !== original.process.pid || info.process?.birth !== original.process.birth)
      throw new VmError(`The VM changed before the original ${effect}. No power action was sent.`);
    const boot = JSON.parse(await readFile(join(projectsDirectory(), '.studio/development/Boots', id + '.json'), 'utf8'));
    if (!boot.connected || boot.vmId !== id || boot.vmRevision !== (info.vm.revision ?? info.vm.imageSha256)
      || boot.bootId !== original.bootId || boot.invocationId !== original.unit.invocationId)
      throw new VmError(`The original VM boot changed before ${effect}.`);
  } else if (proof.kind !== 'vm_restart' || proof.phase !== 'restart_intent' || !proof.stopped?.confirmed
    || !info.fullyStopped || !info.exportComplete || info.originalProcessAlive
    || info.unit.invocationId && info.unit.invocationId !== original.unit.invocationId)
    throw new VmError('Restart requires its original completed stop/export. No start was sent.');
}

export function lifecycleTarget(vm: VirtualMachine, scope: { vmRevision: string; imageId: string; imageSha256: string }) {
  if ((vm.revision ?? vm.imageSha256) !== scope.vmRevision || vm.imageId !== scope.imageId || vm.imageSha256 !== scope.imageSha256)
    throw new VmError('The original VM lifecycle image or revision changed.');
}
