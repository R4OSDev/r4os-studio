export interface MigrationSelection { providerId: string; model: string; effort: string }
export interface SessionMigrationStatus {
  sessionId: string; engine: 'codex' | 'claude-code' | 'studio'; revision: number;
  migration?: { requestId: string; state: 'complete' | 'reverted'; createdAt: string; sourceKind: string;
    records: number; target: MigrationSelection; canRollback: boolean };
}
export interface SessionMigrationPreview extends SessionMigrationStatus {
  allowed: boolean; blockers: string[]; sourceSha256?: string; targetSha256?: string;
  records?: number; archives?: number; opaqueRecordsRetained?: number; target?: MigrationSelection;
}
export interface SessionMigrationInput extends MigrationSelection {
  requestId: string; revision: number; sourceSha256: string; targetSha256: string;
}
