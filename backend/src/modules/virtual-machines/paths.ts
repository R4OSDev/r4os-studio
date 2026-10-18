import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
export const root = process.env.STUDIO_R4OS_DIR ?? fileURLToPath(new URL('../../../../Data/R4OS/', import.meta.url));
export const runtimeRoot = process.env.STUDIO_VM_RUNTIME_DIR ?? '/run/r4os-studio-vms';
export function validId(id: string) { return /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(id); }
export function vmPath(id: string) {
  if (!validId(id)) throw new VmError('Invalid virtual machine ID.', 400);
  return join(root, 'Instances', id);
}
export function runtimePath(id: string) { vmPath(id); return join(runtimeRoot, id); }
export class VmError extends Error { constructor(message: string, public statusCode = 409) { super(message); } }
