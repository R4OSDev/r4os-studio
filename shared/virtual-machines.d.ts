export interface VmImage {
  schema: 1; id: string; version: string; variant: 'full'; architecture: 'x86_64';
  disk: 'disk.img'; sha256: string; diskSizeBytes?: number; diskMtimeMs?: number; sourceUrl?: string; archiveSha256?: string;
}
export interface VmConfig {
  schema: 1; id: string; name: string; imageId: string; imageSha256: string;
  cpus: number; memoryMiB: number; createdAt: string;
}
export type VmState = 'stopped' | 'starting' | 'running' | 'paused' | 'stopping' | 'failed';
export interface VirtualMachine extends VmConfig {
  state: VmState; sharePath: string; shareMode: 'fat32-persistent';
  shareSync?: { pending: boolean; error?: string; lastSyncedAt?: string };
  error?: string;
}
export interface VmFile { name: string; size: number }
export interface VmList { vms: VirtualMachine[]; images: VmImage[]; csrfToken: string; available: boolean }
export interface VmInput { name: string; cpus: number; memoryMiB: number; imageId?: string }

export interface VmPointerInput { dx: number; dy: number; buttons: number }
