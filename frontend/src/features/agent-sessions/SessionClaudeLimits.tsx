import { useEffect, useState } from 'react';
import type { ClaudeSubscriptionLimits, ClaudeRateObservation, ClaudeQuotaHold } from '../../../../shared/claude-subscription';
import { ClaudeLimitsView } from '../llm-providers/components/ClaudeLimitsView';
import { useSessionApi } from './api';

export function SessionClaudeLimits({ base, token, observation = null }: { base: string; token: string; observation?: ClaudeRateObservation | null }) {
  const { request } = useSessionApi();
  const [limits, setLimits] = useState<ClaudeSubscriptionLimits | null>(null);
  const [cachedEvent, setCachedEvent] = useState<ClaudeRateObservation | null>(null);
  const [revision, setRevision] = useState<number>();
  const [hold, setHold] = useState<ClaudeQuotaHold | null>(null);
  useEffect(() => {
    let active = true;
    const read = () => {
      if (document.hidden) return;
      void request<{ limits: ClaudeSubscriptionLimits | null; observation: ClaudeRateObservation | null; hold?: ClaudeQuotaHold | null; providerRevision?: number }>(base + '/claude-limits', token)
        .then(value => { if (active) { setLimits(value.limits); setCachedEvent(value.observation); setHold(value.hold ?? null); setRevision(value.providerRevision); } })
        .catch(() => { if (active) { setLimits(null); setCachedEvent(null); } });
    };
    read(); const timer = setInterval(read, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [base, request, token]);
  const latest = observation && (!cachedEvent || observation.receivedAt >= cachedEvent.receivedAt) ? observation : cachedEvent;
  return <ClaudeLimitsView sample={limits} observation={latest} hold={hold} revision={revision} compact />;
}
