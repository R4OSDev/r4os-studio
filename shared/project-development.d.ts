import type { ProjectPins, ProjectTemplate } from './projects.js';

/** Studio contracts; these are not R4OS ABI or SDK interfaces. */
export type DevelopmentJobKind = 'build' | 'package' | 'update_probe' | 'update_transfer' | 'update_install' | 'update_commit' | 'update_verify' | 'update_recovery' | 'deploy' | 'execution' | 'vm_start' | 'ssh';
export type DevelopmentJobState = 'queued' | 'starting' | 'running' | 'stopping'
  | 'completed' | 'failed' | 'interrupted' | 'unknown';
export type DevelopmentCheckState = 'not-run' | 'passed' | 'failed' | 'inconclusive';
export type DevelopmentToolId = 'studio.build_project' | 'studio.deploy_project' | 'studio.run_project'
  | 'studio.complete_development_job' | 'studio.read_development_job' | 'studio.stop_development_job' | 'studio.capture_vm' | 'studio.send_vm_input' | 'studio.start_project_vm' | 'studio.run_vm_command';

export interface DevelopmentCapability {
  reasonCode?: string | null;
  available: boolean;
  reason?: string;
}
export type DesktopLaunchBudget = {available:false;reason:string} | {available:true;commandBytes:number;limitBytes:number;wrapperBytes:number;fixedBytes:number;
  argumentBytes:number;argumentCapacityBytes:number;remainingArgumentBytes:number;remainingCommandBytes:number;overByBytes:number;waitMilliseconds:number;withinLimit:boolean};
export type DesktopArgumentLayout = {available:false;reason:string} | {available:true;
  binding:{projectRevision:number;settingsRevision:number;deploymentId:string;vmId:string;vmRevision:string;bootId:string};
  limitBytes:number;wrapperBytes:number;defaultWaitFixedBytes:number;shortWaitFixedBytes:Record<string,number>;saved:DesktopLaunchBudget};
export interface DevelopmentOptions {
  sdkInputs?: { available: boolean; path: string; reason?: string; technical?: boolean;
    configSha256?: string | null; additionalLibraries?: string[]; developmentProfile?: string | null };
  keyPlan?: { version: 1; maximumSteps: 32; maximumMilliseconds: 2000; requiresNewDeployment: true; heldKeys: false; heldModifiers: false; delivery: 'owned-event-queue' };
  editorShortcuts?: { version: 1; keys: ['Ctrl+A']; unsupported: ['Ctrl+Home', 'Ctrl+End']; delivery: 'semantic-codepoint'; requiresNewDeployment: true };
  windowControlVersion?: 1;
  desktopLaunchBudget?: DesktopArgumentLayout | null;
  evidenceCapabilities?: {
    exitStatus: { state: 'unconfirmed' | 'conditional'; reasonCode: string; reason: string };
    consoleOutput: { state: 'unconfirmed' | 'conditional'; reasonCode: string; reason: string };
  } | null;
  revision: string;
  build: DevelopmentCapability;
  deploy: DevelopmentCapability;
  execute: DevelopmentCapability;
  capture: DevelopmentCapability;
  input: DevelopmentCapability;
  startVm?: DevelopmentCapability;
  ssh?: DevelopmentCapability & {commandLimitBytes:number;channelLimitBytes:number;interactive:false};
  profileId: string | null;
  assignedVm: { id: string; name: string; imageId: string; ready: boolean } | null;
}

export interface SourceFileIdentity { path: string; sha256: string; bytes: number; executable?: boolean }
export interface DevelopmentSource {
  id: string;
  sha256: string;
  manifestSha256: string;
  files: SourceFileIdentity[];
  directories: string[];
  pins: ProjectPins;
}
export interface ResourceInputReport { schema: 1; available: boolean; stage: 'Registered' | 'Unknown'; reason?: string; sourceSha256?: string; manifestSha256?: string; entries?: { kind: 'icon' | 'help' | 'file'; index: number; name?: string; path: string; bytes: number; sha256: string }[]; unregisteredAssets?: string[]; unregisteredCount?: number; consumerVerified?: boolean; embeddedVerified?: boolean; guestVerified?: boolean }
export interface DevelopmentArtifact {
  sdkProfile?: { id: string; hashes: Record<string, string>; technical: boolean };
  sdkInputs?: DevelopmentSdkInputs;
  resourceInputs?: ResourceInputReport;
  resourceInventory?: { schema: 1; available: boolean; stage: 'Embedded' | 'Unknown'; artifactSha256?: string; sourceSha256?: string; manifestSha256?: string; container?: string; reader?: string; inspectorSha256?: string; entries?: { kind: 'icon' | 'help' | 'file'; index: number; name?: string; path: string; bytes: number; sha256: string; sourceSha256: string; transform?: string }[]; embeddedVerified?: boolean; consumerVerified?: boolean; guestVerified: boolean; reason?: string };
  updateMetadata?: { available: boolean; reason?: string; identity?: import('./update-packages.js').NativeUpdateIdentity; payloadKind?: string; inspectorSha256?: string; adapterSha256?: string; sdkRevision?: string; manifest?: Record<string, unknown> };
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
  desktopEvidence?: { processConfirmed: true; windowVisible: boolean; windowFocused: boolean; contentConfirmed: false; statusPollingBounded: true; statusRetentionExpired: boolean };
  state: 'transferred' | 'ready' | 'started' | 'completed' | 'unsupported' | 'unknown' | 'failed' | 'interrupted';
  reasonCode?: string; reason?: string; checkedAt: string;
  process?: GuestProcessIdentity;
}
export interface DevelopmentTarget {
  updateEpoch?: string | null;
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
  desktopShortcut?: DesktopShortcutReceipt;
  format?: 'exchange-build-v1';
  readiness?: DevelopmentReadiness;
  id: string; projectId: string; jobId: string; artifactId: string;
  packageSha256: string; sourceSha256: string; manifestSha256: string;
  target: DevelopmentTarget; role: ProjectTemplate; kind: DevelopmentArtifact['kind'];
  guestDirectory: string; entry: string; helper: string; helperSourceSha256: string;
  files: { path: string; bytes: number; sha256: string; fullReadbackVerified: boolean }[];
  pins: ProjectPins; createdAt: string;
}
export interface DesktopShortcutReceipt {
  state: 'published'; projectId: string; vmId: string; jobId: string;
  deploymentId: string; artifactId: string; path: string; content: string; sha256: string;
  fullReadbackVerified: true; iconEmbedded: boolean;
  /** A current file observation does not replace a missing native completion. */
  publicationProof?: 'original-desktop-current-files';
  nativeCompletionReceiptAvailable?: false;
  originalHelperExitCode?: 113;
  consumerVerified: false; guestVerified: false; applicationStarted: false; checkedAt: string;
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
  diagnosticOnly?: true; contentUnconfirmed?: true; inputReference?: false; completionReference?: false;
  gestureObservation?: {
    id: string; acceptedBefore: number; acceptedAfter: number;
    activeBefore: true; activeAfter: boolean;
    releaseQueuedBefore: boolean; releaseQueuedAfter: boolean; consumptionConfirmed: false;
  };
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
  /** Original native link proof; never a synthetic DESKRUN request. */
  desktopLinkActivation?: DevelopmentJob['desktopLinkActivation'];
  width?: number;
  height?: number;
  guestRevision?: number;
  windowVisible?: boolean;
  windowFocused?: boolean;
  windowObservation?: {
    instanceId: number; generation: string; windowId: number;
    windowWidth: number; windowHeight: number; windowVisible: boolean; windowFocused: boolean;
  };
  /** The screen was captured between two observations; no atomic guest-frame claim. */
  captureObservation?: {
    version: 1; mode: 'observed-interval'; startedAt: string; completedAt: string;
    elapsedMilliseconds: number; revisionBefore: number; revisionAfter: number; contentChanged: boolean;
  };
}
export interface DevelopmentStopReceipt {
  version: 1; jobId: string; requested: boolean; confirmed: boolean;
  outcome: 'stopped' | 'already-ended' | 'not-started' | 'unconfirmed';
  scope: 'worker' | 'owned-process' | 'ssh-client'; jobState: DevelopmentJobState; recordedAt: string; reason: string;
  guestEffectsMayRemain?: boolean; source?: string; receiptSha256?: string;
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
  sdkInputs?: DevelopmentSdkInputs;
  sdkResolution?: Record<string, unknown>;
  sdkDevelopment?: { sha256: string; sdkSource: Record<string, unknown> } | null;
  sshCommand?: string;
  ssh?: {version:1;command:string;commandBytes:number;commandLimitBytes:number;channelLimitBytes:number;
    sshExitCode:number|null;commandExitCode:number|null;commandReturnConfirmed:boolean;sshClientEndConfirmed:boolean;
    guestProcessEndConfirmed:boolean;guestDescendantsEndConfirmed:false;outputComplete:boolean;startedAt?:string;endedAt?:string;
    outputCompletenessScope?:'received-ssh-streams';nativeOutputComplete?:false|null;nativeOutputLossReported?:boolean;
    channels:Record<'stdout'|'stderr',{bytesReceived:number;bytesCaptured:number;truncated:boolean}>};
  lastKeyPlan?: { keyPlanId: string; accepted: number; expected: number; active: boolean; complete: boolean; queuedAtMilliseconds: number[]; latenessMilliseconds: number[]; abortedReason: string | null; consumptionConfirmed: false };

  desktopLaunchBudget?: DesktopLaunchBudget;
  outputFiles?: { name: string; state?: 'missing' | 'unstable' | 'unconfirmed' | 'observed-stable'; id?: string;
    sha256?: string; bytes?: number; createdAt?: string; containsExpectedText?: boolean; error?: string }[];
  liveFileObservation?: { schema: 1; mode: 'observed-interval'; checkedAt: string; refreshAfterMs: number;
    bootId: string; process: GuestProcessIdentity; deploymentId: string; sessionId: string | null;
    agentRunId: string | null; completionConfirmed: false };
  updatePlan?: import('./update-packages.js').UpdatePackagePlan;
  packageArtifactId?: string | null;
  updateInstallation?: import('./update-packages.js').UpdateInstallation;
  updateTransfer?: import('./update-packages.js').UpdateTransfer;
  updateProbe?: import('./update-packages.js').UpdateProbe;
  updatePackage?: import('./update-packages.js').UpdatePackageArtifact;
  outputBytes?: number;
  reasonCode?: string | null;
  nextStep?: string | null;
  checkCompletion?: { requestId: string; reason: 'criteria_complete'; state: 'closing' | 'completed' | 'failed'; closed?: boolean; completedAt?: string };
  desktopLaunch?: DesktopLaunchReceipt;
  desktopLaunchAttempt?: {
    schema: 1; hostAttemptId: string; jobId: string; projectId: string; executionId: string;
    deploymentId: string; phase: string; createdAt: string; observedAt: string;
    nativeRequest: string | null; nativeRequestConfirmed: boolean;
    source?: 'original-deskrun-transport'; statusOnly?: boolean;
    controlChannelLost?: boolean; nativePhase?: string; nativeErrorlevel?: number;
    process?: { instanceId: number; generation: string } | null;
    transport?: { sshExitCode: number | null; transportUncertain: boolean; localSshProcessId?: number;
      startedAt?: string; observedAt?: string; elapsedMilliseconds?: number; stdoutBytes: number; stderrBytes: number };
  };
  desktopShortcutRequested?: boolean;
  desktopLinkRequested?: boolean;
  desktopLinkActivation?: { version: 1; phase: string; publicationJobId: string; linkPath: string; linkSha256: string;
    originalRequestSha256: string | null; native: Record<string, unknown> | null; checkedAt: string };
  desktopShortcut?: DesktopShortcutReceipt;
  windowControlRequested?: boolean;
  windowControl?: { version: number; available: boolean; operationId?: string; reason?: string; native?: Record<string, unknown> };
  package?: { format: 'exchange-build-v1' | 'legacy-c'; relativeDirectory: string; guestDirectory: string };

  vmStart?: {
    ready: boolean; started: boolean; checkedAt?: string; guestRelease?: string; guestKernel?: string;
    vmId?: string; vmRevision?: string; imageId?: string; imageSha256?: string; bootId?: string; accessRevision?: number;
  };
  readiness?: DevelopmentReadiness;
  guestState?: { closeConfirmed?: boolean; [key: string]: unknown };
  recovery?: { id: string; source: string; reason?: string; replayed: false; guestEndConfirmed?: boolean;
    publicationReadbackConfirmed?: true; nativeCompletionReceiptAvailable?: false; originalHelperExitCode?: 113 };
  settingsRevision: number;
  id: string;
  projectId: string;
  kind: DevelopmentJobKind;
  requestId?: string;
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
  artifactSummary?: { id: string; kind?: DevelopmentArtifact['kind']; role?: ProjectTemplate };
  startOffset?:number;pageBytes?:number;totalBytes?:number;hasMore?:boolean;
  captureLimitReached?:boolean;captureTruncated?:boolean|null;outputEncoding?:'utf-8'|'replacement';rawOutputBase64?:string;
  executionEvidence?: DevelopmentExecutionEvidence | null;
  job: DevelopmentJob;
  output: string;
  nextOffset: number;
  truncated: boolean;
  /** SSH console transport does not imply independently captured stderr. */
  outputKind: 'build' | 'console' | 'diagnostic';
  evidence: DevelopmentEvidence[];
}
/** Independent findings read from matching private originals; grants no lifecycle action. */
export interface DevelopmentExecutionEvidence {
  version: 1;
  source?: 'private-guest-close-receipt' | 'private-guest-observation' | 'native-retained-completion';
  processEndConfirmed: boolean;
  cleanupConfirmed: boolean;
  exitStatusConfirmed: boolean;
  exitCode: number | null;
  exitStatusReason?: string;
  output: { state: 'complete' | 'incomplete' | 'unconfirmed'; reason: string; bytes?: number; sha256?: string };
}
export interface DevelopmentSdkInputs {
  schema: 1;
  technical: boolean;
  configSha256: string | null;
  additionalLibraries: { id: string; root: string; path?: string; commit?: string; tree?: { algorithm: string; files: string[]; sha256: string } }[];
  development: { sdkRoot: string; contractRoot?: string; librariesRoot?: string; profile: string } | null;
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
