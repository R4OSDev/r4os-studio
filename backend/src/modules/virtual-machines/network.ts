import { readFile } from 'node:fs/promises';
import { VmError } from './paths.js';

export async function networkAvailable() {
  try {
    const capability = JSON.parse(await readFile(process.env.STUDIO_VM_NETWORK_CAPABILITY ?? '/etc/r4os-studio-vms/network.json', 'utf8'));
    return capability.schema === 1 && capability.mode === 'user' && capability.device === 'e1000';
  } catch { return false; }
}
export async function networkArguments(id: string, enabled: boolean | undefined): Promise<string[]> {
  if (!enabled) return ['-nic', 'none'];
  if (!await networkAvailable()) throw new VmError('VM network host support is not installed. See the host setup documentation.');
  // Stable locally administered unicast address; the guest obtains DHCP from SLIRP.
  const suffix = id.replaceAll('-', '').slice(-10).match(/../g)!.join(':');
  return ['-netdev', 'user,id=studio-net,ipv6=off', '-device', `e1000,netdev=studio-net,mac=02:${suffix}`];
}
