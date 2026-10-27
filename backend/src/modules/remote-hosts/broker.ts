/** Private fixed protocol for the forthcoming unprivileged SSH/SFTP broker.
 * Public requests select saved IDs/revisions, never SSH options or credentials.
 * No connection is opened by catalog management.
 */
export interface RemoteTargetBinding {
  hostId: string; endpointRevision: number; credentialRevision: number; trustRevision: number;
}
export type RemoteBrokerRequest = { protocol: 1; operation: 'capabilities' }
  | { protocol: 1; operation: 'test'; requestId: string; binding: RemoteTargetBinding }
  | { protocol: 1; operation: 'read'; requestId: string };
export interface RemoteBrokerCapabilities { protocol: 1; test: boolean; commands: boolean; files: boolean }
