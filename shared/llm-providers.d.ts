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
