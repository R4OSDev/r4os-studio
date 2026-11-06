export type ComponentKind = 'sdk' | 'contract' | 'libraries' | 'zig' | 'rust' | 'qemu' | 'codex' | 'r4upack' | 'r4os';
export interface SdkSetPart {
  version: string; revision: string; sourceUrl: string; url: string; sha256: string; bytes: number;
  packageHash?: string; installed: boolean; active: boolean;
}
export interface SdkSet {
  state: 'unresolved' | 'unavailable' | 'ready'; reason?: string;
  manifestUrl?: string; manifestSha256?: string; complete?: boolean; active?: boolean;
  interface?: 'r4os-sdk-package';
  profileSources?: Record<'Build' | 'Tools' | 'Components', string>;
  buildProfiles?: Record<string, { language: string; role: string; codegen: string; toolset: string; components: string; cpu?: string }>;
  toolsets?: Record<string, { tools: string[] }>;
  componentSets?: Record<string, { contract: string; system_libraries: string[] }>;
  components?: Record<'sdk' | 'contract' | 'libraries', SdkSetPart>;
}
export interface ComponentVersion {
  id: string; version: string; revision?: string; sha256?: string; packageHash?: string;
  sourceUrl?: string; minZigVersion?: string; installedAt?: string; external?: boolean;
  dependencies?: { contract?: { revision: string; packageHash: string } };
  cargoVersion?: string; host?: string; targets?: string[]; manifestSha256?: string;
  toolchainProfile?: string; sdkVersion?: string;
  sdkSet?: SdkSet;
  sdkRevision?: string; profileSha256?: string;
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
  features?: { sdkSets?: number; sdkSelection?: number; sdkProfiles?: number; componentProgress?: number }; profileRevision?: string;
  generation?: string;
  inventory?: { revision: string | null; checkedAt: string; reused: boolean };
  sdkOperation?: { requestId: string; phase: 'complete' };
}
export interface ComponentsProgress {
  enabled: boolean; job: ComponentJob | null; profileRevision: string; generation: string;
  inventoryRevision: string | null; features: { componentProgress: number };
}
