export interface ProjectSummary {
  id: string;
  name: string;
}

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
}
export interface ProjectOptions {
  revision: string; profile: ProjectPins;
  languages: { id: ProjectLanguage; available: boolean; reason?: string }[];
  moduleTypes: { id: ProjectTemplate; label: string; kind: string; appClass: string | null;
    languages: ProjectLanguage[]; available: boolean }[];
  vms: { id: string; name: string }[]; vmsAvailable: boolean;
}
