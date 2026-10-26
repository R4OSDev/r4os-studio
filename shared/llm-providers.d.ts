export interface Provider {
  id: string;
  name: string;
  type: 'openai';
  status: 'connected' | 'disconnected' | 'signing_in' | 'unavailable';
  account: { email: string | null; plan: string | null } | null;
  createdAt: string;
}

export interface ProviderLogin {
  status: 'pending' | 'connected' | 'cancelled' | 'failed' | 'expired';
  verificationUrl?: string;
  userCode?: string;
  expiresAt: string;
  message?: string;
}

export interface ProviderList {
  providers: Provider[];
  csrfToken: string;
  signInAvailable: boolean;
}

export interface UsageWindow {
  usedPercent: number | null;
  remainingPercent: number | null;
  windowDurationMins: number | null;
  resetsAt: string | null;
}

/** Native Codex credit units, independent of earned resets and API billing. */
export interface CreditBalance {
  hasCredits: boolean | null;
  unlimited: boolean | null;
  /** Validated bounded numeric text; never coerced to a JavaScript number. */
  balance: string | null;
}

export interface UsageLimit {
  credits?: CreditBalance | null;
  id: string;
  name: string;
  primary: UsageWindow | null;
  secondary: UsageWindow | null;
  limitReached: boolean;
}

export interface ResetCredit {
  id: string;
  type: 'codexRateLimits' | 'unknown';
  status: 'available' | 'redeeming' | 'redeemed' | 'unknown';
  title: string | null;
  description: string | null;
  grantedAt: string | null;
  expiresAt: string | null;
}

/** Studio adapter capability; null is unknown spending state, never disabled. */
export interface CreditUsageControl {
  supported: false;
  enabled: null;
  reason: 'not-exposed-by-supported-native-interface';
}

export interface ProviderUsage {
  creditUsageControl?: CreditUsageControl;
  fetchedAt: string;
  ordinaryUsageAllowed: boolean | null;
  limits: UsageLimit[];
  resetCredits: { availableCount: number | null; credits: ResetCredit[] | null } | null;
}

export type ResetOutcome = 'reset' | 'alreadyRedeemed' | 'nothingToReset' | 'noCredit';

export interface ResetRequest {
  confirm: true;
  idempotencyKey: string;
  creditId?: string;
}

export interface ResetResult {
  outcome: ResetOutcome;
  usage: ProviderUsage | null;
}
