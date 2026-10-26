import type { ProjectPins } from './projects.js';
import type { DevelopmentArtifact, SourceFileIdentity } from './project-development.js';

/** Studio package orchestration; native R4OS remains the format authority. */
export interface UpdatePackageMetadata {
  packageId: string; packageVersion: string; targetRelease: string; title: string; description: string;
}
export interface UpdateRequirement {
  kind: 'KERNEL' | 'R4X' | 'R4L' | 'R4D' | 'R4P';
  name: string; target: string; minVersion: string; state: 'installed' | 'active'; spec?: string;
}
export interface NativeUpdateIdentity {
  schema: 1; kind: UpdateRequirement['kind']; name: string; version: string;
  target: string; activation: 'live' | 'restart'; priority: 'normal' | 'foundation';
}
export interface UpdatePayload {
  artifactId: string; buildId: string; file: SourceFileIdentity;
  kind: 'software' | 'service' | 'system-library' | 'driver' | 'protocol' | 'boot-kernel';
  target: string; canonicalTarget: string; component: NativeUpdateIdentity;
  sourceSha256: string; manifestSha256: string; artifactPackageSha256: string;
  buildProof: DevelopmentArtifact['buildProof']; nativeInspectorSha256: string; nativeAdapterSha256: string;
}
export interface UpdatePackerPin {
  id: string; version: string; revision: string; sdkRevision: string;
  host: string; sha256: string; profileSha256: string;
}
export interface UpdatePackagePlan {
  schema: 1; id: string; sha256: string; projectId: string; projectRevision: number;
  configurationRevision: number; createdAt: string; metadata: UpdatePackageMetadata;
  payloads: UpdatePayload[]; requirements: UpdateRequirement[]; pins: ProjectPins; packer: UpdatePackerPin;
  activation: 'live' | 'restart'; priority: 'normal' | 'foundation';
  manifestByteUpperBound: number; containerByteUpperBound: number;
  batch: { packages: number; components: number; requirements: number };
  nativeValidation: 'required-at-build'; targetReleaseSource: 'explicit-offline-selection';
}
export interface UpdatePlanInput {
  requestId: string; projectRevision: number; configurationRevision: number;
  metadata: UpdatePackageMetadata; artifactIds: string[]; requirements: UpdateRequirement[];
}
export interface UpdatePackageOptions {
  projectRevision: number;
  settings: { revision: number; metadata: UpdatePackageMetadata | null; requirements: UpdateRequirement[] };
  limits: { payloads: number; requirements: number; manifestBytes: number; packageBytes: number;
    nativeContainerBytes: number; batchPackages: number; batchComponents: number; batchRequirements: number };
  artifacts: DevelopmentArtifact[]; plans: UpdatePackagePlan[];
}


export interface UpdatePackageArtifact {
  schema: 1; id: string; projectId: string; jobId: string; plan: UpdatePackagePlan;
  bytes: number; sha256: string; format: 'R4U2'; createdAt: string; nativeExitCode: 0;
  packer: UpdatePackerPin; diagnostics: { jobId: string; outputBytes: number; stdoutBytes: number; stderrBytes: number }; arguments: string[];
}
export interface UpdatePackageBuildInput {
  requestId: string; projectRevision: number; planId: string; planSha256: string;
}


export interface UpdateCommandCapture {
  exitCode: number | null; stdout: string; stderr: string; stdoutBytes: number; stderrBytes: number;
  truncated: boolean; timedOut: boolean; transportUncertain?: boolean;
}
export interface SysupdReply {
  schema: 1; operation: string; effectiveOperation: string; kind: 'status' | 'result';
  confirmed: boolean; success: boolean; sshExitCode: number | null; rawLine: string;
  reportedOutcome?: 'rolled-back' | 'pending-restart' | 'installed' | 'staged' | 'applied' | 'unknown'; installationConfirmed?: false;
  result?: 'OK' | 'FAILED' | 'INCOMPATIBLE' | 'INTERRUPTED'; fields?: Record<string, string>;
  status?: { mode: 'idle' | 'journal' | 'batch'; fields: Record<string, string>;
    transactionId: string | null; batchId: string | null; journalPhase?: string; batchPhase?: string;
    directoriesReady: boolean; activeOrRecoverable: boolean; historicalRollback: boolean };
}
export interface UpdateProbe {
  schema: 1; adapterSha256: string; state: 'capturing' | 'ready' | 'blocked'; mayUpload: boolean; statusCreatesDirectories: true;
  captures: Record<string, UpdateCommandCapture>; status?: SysupdReply;
  installedRelease?: string; activeKernel?: string; baseImageId?: string; baseImageSha256?: string;
  requestedTargetRelease?: string; checkedAt?: string; hostKeyFingerprint?: string;
  target?: { vmId: string; vmRevision: string; imageId: string; imageSha256: string; bootId: string;
    systemGeneration: string | null; vmInvocationId: string };
  inventory?: { schema: number; profile: string; count: number; entries: Record<string, unknown>[] };
  inventoryRead?: { method: string; consoleIncomplete: boolean; reads: { bytes: number; sha256: string; fullReadVerified: true }[] };
  ownership?: { matchesOwnRecord: boolean; activeOrRecoverable: boolean; mayUpload: boolean;
    reason: string | null; terminalHistoryRetained: boolean; externalWriterLock: false };
  nativeVerificationRequired?: true;
}
