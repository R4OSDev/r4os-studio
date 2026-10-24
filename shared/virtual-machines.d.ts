export interface VmImage {
  schema: 1; id: string; version: string; variant: 'full'; architecture: 'x86_64';
  disk: 'disk.img'; sha256: string; diskSizeBytes?: number; diskMtimeMs?: number; sourceUrl?: string; archiveSha256?: string;
}
export interface VmConfig {
  schema: 1; id: string; name: string; imageId: string; imageSha256: string;
  cpus: number; memoryMiB: number; networkEnabled?: boolean; revision?: string; systemGeneration?: string; createdAt: string;
}
export type VmState = 'stopped' | 'starting' | 'running' | 'paused' | 'stopping' | 'failed';
export interface VirtualMachine extends VmConfig {
  state: VmState; sharePath: string; shareMode: 'fat32-persistent';
  shareSync?: { pending: boolean; error?: string; lastSyncedAt?: string };
  error?: string;
}
export interface VmFile { name: string; size: number; kind?: 'file' | 'directory' }
export interface VmList { vms: VirtualMachine[]; images: VmImage[]; defaultImageId: string | null; csrfToken: string; available: boolean; networkAvailable: boolean }
export interface VmInput { name: string; cpus: number; memoryMiB: number; imageId?: string; networkEnabled?: boolean }

export interface VmPointerInput { dx: number; dy: number; buttons: number }

export interface VmReleaseChange {
  confirm: true; expectedRevision: string; expectedImageId: string; expectedImageSha256: string;
  imageId: string; imageSha256: string;
}

export interface VmResetInput {
  kind: 'system' | 'exchange'; requestId: string; expectedRevision: string; confirm: true;
}

export interface VmDevelopmentAccess {
  revision: number; vmRevision: string; enabled: boolean; username: string;
  credentialPolicy: 'r4os-default-v1'; hostKeyFingerprint: string | null; imageId: string;
  available: boolean; ready: boolean; reason: string | null; lastCheckedAt: string | null;
  guestRelease: string | null; guestKernel: string | null;
}
export interface VmDevelopmentAccessInput {
  revision: number; vmRevision: string; enabled: boolean; resetHostKey?: boolean;
}
