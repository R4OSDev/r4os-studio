import type { ProjectPins, ProjectTemplate } from './projects.js';

/** Studio contracts; these are not R4OS ABI or SDK interfaces. */
export type DevelopmentJobKind = 'build' | 'deploy' | 'execution' | 'vm_start';
export type DevelopmentJobState = 'queued' | 'starting' | 'running' | 'stopping'
  | 'completed' | 'failed' | 'interrupted' | 'unknown';
export type DevelopmentCheckState = 'not-run' | 'passed' | 'failed' | 'inconclusive';
export type DevelopmentToolId = 'studio.build_project' | 'studio.deploy_project' | 'studio.run_project'
  | 'studio.complete_development_job' | 'studio.read_development_job' | 'studio.stop_development_job' | 'studio.capture_vm' | 'studio.send_vm_input' | 'studio.start_project_vm';

export interface DevelopmentCapability {
  reasonCode?: string | null;
  available: boolean;
  reason?: string;
}
export interface DevelopmentOptions {
  revision: string;
  build: DevelopmentCapability;
  deploy: DevelopmentCapability;
  execute: DevelopmentCapability;
  capture: DevelopmentCapability;
  input: DevelopmentCapability;
  startVm?: DevelopmentCapability;
  profileId: string | null;
  assignedVm: { id: string; name: string; imageId: string; ready: boolean } | null;
}

export interface SourceFileIdentity { path: string; sha256: string; bytes: number }
export interface DevelopmentSource {
  id: string;
  sha256: string;
  manifestSha256: string;
  files: SourceFileIdentity[];
  directories: string[];
  pins: ProjectPins;
}
export interface DevelopmentArtifact {
  id: string;
  projectId: string;
  buildId: string;
  sourceSha256: string;
  manifestSha256: string;
  packageSha256: string;
  kind: 'R4X' | 'R4L' | 'R4D' | 'R4P';
  role: ProjectTemplate;
  entry: string;
  files: SourceFileIdentity[];
  createdAt: string;
  buildProof: { format: string; sha256: string; bytes: number };
}
export interface DevelopmentExchangeTarget {
  schema: 1; vmId: string; generation: string; markerSha256: string;
  drive: string; bootId: string; accessRevision: number;
}
export interface DevelopmentReadiness {
  state: 'transferred' | 'ready' | 'started' | 'completed' | 'unsupported' | 'unknown' | 'failed' | 'interrupted';
  reasonCode?: string; reason?: string; checkedAt: string;
  process?: GuestProcessIdentity;
}
export interface DevelopmentTarget {
  exchange?: DevelopmentExchangeTarget;
  vmId: string;
  vmRevision: string;
  imageId: string;
  imageSha256: string;
  bootId: string;
  profileId: string;
  helperSha256: string;
  helperProtocol: number;
}
export interface DevelopmentDeployment {
  format?: 'exchange-build-v1';
  readiness?: DevelopmentReadiness;
  id: string; projectId: string; jobId: string; artifactId: string;
  packageSha256: string; sourceSha256: string; manifestSha256: string;
  target: DevelopmentTarget; role: ProjectTemplate; kind: DevelopmentArtifact['kind'];
  guestDirectory: string; entry: string; helper: string; helperSourceSha256: string;
  files: { path: string; bytes: number; sha256: string; fullReadbackVerified: boolean }[];
  pins: ProjectPins; createdAt: string;
}
export interface GuestProcessIdentity {
  instanceId: number;
  /** Decimal string: R4OS generations are u64, beyond JavaScript integer precision. */
  generation: string;
  windowId?: number;
  serviceName?: string;
}
export interface DesktopLaunchReceipt {
  adapter: 'DESKRUN';
  contract: '0.1.1';
  /** Original opaque Broker-ID:generation:Helper-ID:generation query key. */
  request: string;
  phase: 'request' | 'accepted' | 'starting' | 'process' | 'window' | 'content';
  error: string;
  errorlevel: number;
  process_id: number;
  /** Decimal strings preserve native unsigned 64-bit counters exactly. */
  process_generation: string;
  content: string;
  /** Native Desktop slot plus one; zero means no window receipt. */
  window: number;
  raw: number;
  /** Launch/wait completion, never application termination. */
  terminal: boolean;
  checkedAt: string;
  sshExitCode?: number;
  transportUncertain?: boolean;
  statusError?: string;
  statusErrorlevel?: number;
}
export interface DevelopmentEvidence {
  id: string;
  kind: 'console' | 'diagnostic' | 'screenshot' | 'file';
  name?: string;
  sha256: string;
  bytes: number;
  createdAt: string;
  bootId?: string;
  process?: GuestProcessIdentity;
  desktopRequest?: string;
  desktopContent?: string;
  desktopWindow?: number;
  width?: number;
  height?: number;
}
export interface DevelopmentCheck {
  state: DevelopmentCheckState;
  criteria: { expectedExitCode?: number; outputContains?: string[]; visual?: string };
  findings: string[];
  evidenceIds: string[];
  /** Visual judgement is distinguished from host assertions. */
  assessment: 'host' | 'agent' | 'user' | null;
}
export interface DevelopmentJob {
  checkCompletion?: { requestId: string; reason: 'criteria_complete'; state: 'closing' | 'completed' | 'failed'; closed?: boolean; completedAt?: string };
  desktopLaunch?: DesktopLaunchReceipt;
  package?: { format: 'exchange-build-v1' | 'legacy-c'; relativeDirectory: string; guestDirectory: string };

  vmStart?: {
    ready: boolean; started: boolean; checkedAt?: string; guestRelease?: string; guestKernel?: string;
    vmId?: string; vmRevision?: string; imageId?: string; imageSha256?: string; bootId?: string; accessRevision?: number;
  };
  readiness?: DevelopmentReadiness;
  guestState?: { closeConfirmed?: boolean; [key: string]: unknown };
  recovery?: { id: string; source: string; reason?: string; replayed: false; guestEndConfirmed?: boolean };
  settingsRevision: number;
  id: string;
  projectId: string;
  kind: DevelopmentJobKind;
  source: Omit<DevelopmentSource, 'files' | 'directories'> | null;
  state: DevelopmentJobState;
  revision: number;
  sessionId: string | null;
  agentRunId: string | null;
  artifactId: string | null;
  deploymentId: string | null;
  target: DevelopmentTarget | null;
  process: GuestProcessIdentity | null;
  exitCode: number | null;
  error: string | null;
  phase: string;
  check: DevelopmentCheck | null;
  createdAt: string;
  completedAt: string | null;
}
export interface DevelopmentJobPage {
  job: DevelopmentJob;
  output: string;
  nextOffset: number;
  truncated: boolean;
  /** SSH console transport does not imply independently captured stderr. */
  outputKind: 'build' | 'console' | 'diagnostic';
  evidence: DevelopmentEvidence[];
}
export interface DevelopmentSettings {
  revision: number;
  arguments: string;
  /** '.' selects the role's native default: package for terminal/service,
   * Desktop-owned CWD for DESKRUN. Output files always refer to the package. */
  workingDirectory: string;
  timeoutSeconds: number;
  expectedExitCode: number | null;
  outputContains: string[];
  visualCriteria: string;
  outputFiles: { name: string; contains: string | null; sha256: string | null }[];
  serviceResponseContains: string | null;
}

/** The server derives project and VM scope; none of these accept a host path or VM ID. */
export interface DevelopmentSubmission {
  requestId: string;
  projectRevision: number;
  settingsRevision: number;
}
export interface DevelopmentBuildInput extends DevelopmentSubmission {
  artifactId?: never;
}
export interface DevelopmentDeployInput extends DevelopmentSubmission {
  artifactId: string;
}
export interface DevelopmentRunInput extends DevelopmentSubmission {
  deploymentId: string;
}
