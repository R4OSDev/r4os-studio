export interface StudioRelease { version: string; tag: string; commit: string }
export interface UpdateStatus {
  enabled: boolean;
  installed: { version: string; commit: string | null };
  latest: StudioRelease | null;
  available: boolean;
  source: string;
  phase: string;
  message: string;
  error: string | null;
  lastChecked: string | null;
  nextCheck: string | null;
  checkIntervalSeconds: number;
  history: { version: string; outcome: string; time: string; message: string }[];
  csrfToken?: string;
}
