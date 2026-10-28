/** Exact decimal strings keep lifetime sums lossless beyond JS integer range. */
export interface StatisticsSnapshot {
  schema: 1;
  tokens: Record<'total' | 'input' | 'output' | 'cachedInput' | 'cacheWrite' | 'reasoningOutput', string | null>;
  longestGoalMs?: number | null;
  coverage: { state: 'notReported' | 'partial' | 'unavailable'; since: string | null; updatedAt: string | null; historicalComplete: boolean; hasGaps: boolean; delayed?: boolean };
}
export interface GoalClockSnapshot { executionId: string; durationMs: number; state: 'running' | 'ended' | 'unknown'; referenceAt: string; sampledAt: string; staleAfterMs: number; ageMs: number }
