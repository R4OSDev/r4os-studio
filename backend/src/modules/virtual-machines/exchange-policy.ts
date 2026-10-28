import { readFileSync } from 'node:fs';

// Shared by the exporter, deployment preflight and browser. The immutable VM
// worker release advertises its own copy, including the old, smaller limits.
export const exchangePolicy = JSON.parse(readFileSync(new URL('../../../../shared/exchange-host.json', import.meta.url), 'utf8')) as {
  limits: { files: number; bytes: number; directories: number; depth: number; syncSeconds: number };
  image: { offsetBytes: number; partitionBytes: number; legacyBytes: number };
  stopSeconds: number;
};
export const exchangeLimits = { ...exchangePolicy.limits, seconds: exchangePolicy.limits.syncSeconds };
export const exchangeImageBytes = exchangePolicy.image.offsetBytes + exchangePolicy.image.partitionBytes;
export const supportedExchangeImage = (size: number) => size === exchangeImageBytes || size === exchangePolicy.image.legacyBytes;
