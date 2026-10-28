export interface RemoteHost {
  id: string;
  name: string;
  description: string;
  address: string;
  port: number;
  user: string;
  revision: number;
  endpointRevision: number;
  credentialRevision: number;
  trustRevision: number;
  passwordConfigured: boolean;
  hostKey: { state: 'unbound' | 'trusted'; fingerprint: string | null; trustedAt: string | null };
  lastTest: { status: 'success' | 'offline' | 'authentication_failed' | 'hostkey_changed' | 'not_r4os' | 'transport_error' | 'timeout'; checkedAt: string;
    endpointRevision: number; credentialRevision: number; trustRevision: number; version?: string; kernel?: string } | null;
  createdAt: string;
  updatedAt: string;
}
export interface RemoteHostInput {
  requestId: string;
  name: string;
  description?: string;
  address: string;
  port?: number;
  user?: string;
  password?: string;
}
export interface RemoteHostChange extends Partial<Omit<RemoteHostInput, 'requestId'>> { requestId: string; revision: number }
export interface RemoteHostRemoval { requestId: string; revision: number; confirm: true }
export interface RemoteHostList { hosts: RemoteHost[]; csrfToken: string }
export interface RemoteHostCheck { requestId: string; hostId: string; phase: 'accepted' | 'connecting' | 'complete' | 'unknown'; createdAt: string; updatedAt: string;
  host?: RemoteHost; invalidated?: boolean; message?: string }
export interface RemoteHostCapabilities { protocol: 1; test: boolean; commands: boolean; files: boolean; lifecycle?: 1; reason?: string }
export interface RemoteJobSummary {
  id: string; requestId: string; projectId: string; projectName: string; sessionId: string; hostId: string; hostName: string;
  operation: string; state: 'queued' | 'starting' | 'running' | 'stopping' | 'completed' | 'failed' | 'unknown' | 'unknown_reviewed';
  phase: string; commandPreview: string; action?: string; createdAt: string; updatedAt: string;
}
export interface RemoteJobDetail extends Omit<RemoteJobSummary, 'projectName' | 'commandPreview'> {
  command?: string; transfer?: Record<string, unknown>; result?: Record<string, unknown> | null;
  review?: { requestId: string; reviewedAt: string; originalOutcome: 'unknown'; message: string };
  endpointIdentity?: { address: string; port: number; addresses: string[]; connectAddress: string };
}
export interface RemoteReviewInput { requestId: string; expectedUpdatedAt: string; confirmUnknown: true }
export interface RemoteReviewReceipt { requestId: string; projectId: string; hostId: string; jobId: string; state: 'unknown_reviewed'; originalOutcome: 'unknown'; reviewedAt: string; remoteProcessEndConfirmed: false }
