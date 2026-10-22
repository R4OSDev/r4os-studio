export interface ProjectSummary {
  id: string;
  name: string;
  deleting?: boolean;
}
export interface ProjectDeleted { id: string; deleted: true }

export interface ProjectsResponse {
  projects: ProjectSummary[];
  csrfToken: string;
}

export type ProjectLanguage = 'Rust' | 'Zig' | 'C';
export type ProjectTemplate = 'terminal' | 'desktop' | 'service' | 'driver' | 'protocol' | 'library' | 'subsystem';
export interface ProjectPins {
  sdk: { version: string; revision: string; sha256: string; zigPackageHash: string; url: string };
  contract: { version: string; revision: string; sha256: string; zigPackageHash: string; url: string };
  zig: { version: string; sha256: string; binarySha256: string; url: string };
  rust?: { id: string; version: string; cargoVersion: string; sha256: string;
    toolProfileSha256: string; binarySha256: string; cargoSha256: string; linkerSha256: string;
    powershellSha256: string; installationSha256: string; sysrootSha256: string;
    rustupVersion: string; powershellVersion: string; target: string; codegenProfile: string;
    codegenSha256: string; cpuBaselineSha256: string;
    release: { url: string; sha256: string; sdkRevision: string; contractRevision: string;
      devkitRevision: string; capabilitiesSha256: string } };
}
export interface ProjectOptions {
  revision: string; profile: ProjectPins;
  languages: { id: ProjectLanguage; available: boolean; reason?: string;
    supported?: boolean; toolsAvailable?: boolean; executionQualified?: boolean }[];
  moduleTypes: { id: ProjectTemplate; label: string; kind: string; appClass: string | null;
    languages: ProjectLanguage[]; available: boolean; reasons?: Partial<Record<ProjectLanguage, string>> }[];
  vms: { id: string; name: string }[]; vmsAvailable: boolean;
}

export interface ProjectInput {
  name: string; description: string; language: ProjectLanguage; template: ProjectTemplate;
  vmId: string | null; optionsRevision: string; requestId: string; guestFormats: string[];
}
export interface Project extends ProjectSummary {
  description: string; language: ProjectLanguage; template: ProjectTemplate; moduleName: string;
  vmId: string | null; pins: ProjectPins; revision: number; createdAt: string; updatedAt: string;
}
export interface ProjectUpdate {
  revision: number; name?: string; description?: string; vmId?: string | null;
}
