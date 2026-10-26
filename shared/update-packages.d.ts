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
