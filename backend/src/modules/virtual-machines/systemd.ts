import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { validId, VmError } from './paths.js';
import { exchangePolicy } from './exchange-policy.js';
export const exec = promisify(execFile);
function unit(id: string) {
  if (!validId(id)) throw new VmError('Invalid virtual machine ID.', 400);
  return `r4os-studio-vm@${id}.service`;
}
export async function unitState(id: string) {
  const { stdout } = await exec('/usr/bin/systemctl', ['show', unit(id), '--property=ActiveState,SubState,Result'], { timeout: 10_000 });
  return Object.fromEntries(stdout.trim().split('\n').map((line) => line.split('=')));
}
export async function unitStates(ids: string[]) {
  const result = new Map<string, Record<string, string>>();
  for (let offset = 0; offset < ids.length; offset += 32) {
    const batch = ids.slice(offset, offset + 32), names = batch.map(unit);
    const { stdout } = await exec('/usr/bin/systemctl', ['show', ...names, '--property=Id,ActiveState,SubState,Result'], { timeout: 10_000, maxBuffer: 256 * 1024 });
    const records = stdout.trim().split(/\n\s*\n/).map(block => Object.fromEntries(block.split('\n').map(line => line.split('='))));
    for (const [index, name] of names.entries()) {
      const record = records.find(value => value.Id === name);
      if (!record || !['active', 'activating', 'inactive', 'deactivating', 'failed', 'reloading', 'maintenance', 'refreshing'].includes(record.ActiveState))
        throw new VmError('The VM service states could not be verified. Refresh the view or check the host setup.', 503);
      result.set(batch[index], record);
    }
  }
  return result;
}
export async function control(id: string, action: 'start' | 'stop') {
  try { await exec('/usr/bin/systemctl', ['--no-ask-password', action, unit(id)], { timeout: action === 'stop' ? (exchangePolicy.stopSeconds + 30) * 1000 : 60_000 }); }
  catch { throw new VmError('The VM service could not be controlled. Check VM logs and the host setup.'); }
}
