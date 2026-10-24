export type ComponentKind = 'sdk' | 'contract' | 'libraries' | 'zig' | 'rust' | 'qemu' | 'codex' | 'r4os';
export interface SdkSetPart {
  version: string; revision: string; sourceUrl: string; url: string; sha256: string; bytes: number;
  packageHash?: string; installed: boolean; active: boolean;
}
export interface SdkSet {
  state: 'unresolved' | 'unavailable' | 'ready'; reason?: string;
  manifestUrl?: string; manifestSha256?: string; complete?: boolean; active?: boolean;
  components?: Record<'sdk' | 'contract' | 'libraries', SdkSetPart>;
}
export interface ComponentVersion {
  id: string; version: string; revision?: string; sha256?: string; packageHash?: string;
  sourceUrl?: string; minZigVersion?: string; installedAt?: string; external?: boolean;
  dependencies?: { contract?: { revision: string; packageHash: string } };
  cargoVersion?: string; host?: string; targets?: string[]; manifestSha256?: string;
  toolchainProfile?: string; sdkVersion?: string;
  sdkSet?: SdkSet;
}
export interface ComponentInventory {
  installed: ComponentVersion[]; available: ComponentVersion[]; activeId: string | null;
  latestId: string | null; checkedAt: string | null; error: string | null; hasMore: boolean;
}
export interface ComponentJob {
  kind: ComponentKind; action: 'check' | 'download' | 'default'; phase: 'working' | 'complete' | 'failed';
  message: string; error: string | null; received?: number; total?: number;
  requestId?: string;
}
export interface ComponentsStatus {
  enabled: boolean; components: Record<ComponentKind, ComponentInventory>; job: ComponentJob | null;
  message: string; csrfToken?: string;
  features?: { sdkSets?: number; sdkSelection?: number }; profileRevision?: string;
}
