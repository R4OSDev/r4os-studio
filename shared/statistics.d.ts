/** Exact decimal strings keep lifetime sums lossless beyond JS integer range. */
export interface StatisticsSnapshot {
  totalGoalRuntime?: GoalTotalSnapshot;
  schema: 1;
  tokens: Record<'total' | 'input' | 'output' | 'cachedInput' | 'cacheWrite' | 'reasoningOutput', string | null>;
  longestGoalMs?: number | null;
  coverage: { state: 'notReported' | 'partial' | 'unavailable'; since: string | null; updatedAt: string | null; historicalComplete: boolean; hasGaps: boolean; delayed?: boolean };
}
export interface GoalClockSnapshot { executionId: string; durationMs: number; state: 'running' | 'ended' | 'unknown'; referenceAt: string; sampledAt: string; staleAfterMs: number; ageMs: number }
export interface GoalTotalSnapshot { schema: 1; durationMs: string | null; state: 'running' | 'idle' | 'unknown'; referenceAt: string; sampledAt: string | null;
  live: { executionId: string; ageMs: number; staleAfterMs: number } | null;
  coverage: { state: 'complete' | 'partial' | 'unavailable'; measuredExecutions: number; missingExecutions: number; reasons: string[] } }
