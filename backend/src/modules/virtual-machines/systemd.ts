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
export async function control(id: string, action: 'start' | 'stop') {
  try { await exec('/usr/bin/systemctl', ['--no-ask-password', action, unit(id)], { timeout: action === 'stop' ? (exchangePolicy.stopSeconds + 30) * 1000 : 60_000 }); }
  catch { throw new VmError('The VM service could not be controlled. Check VM logs and the host setup.'); }
}
