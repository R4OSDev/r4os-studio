export class ProviderError extends Error {
  constructor(message: string, readonly statusCode = 400) { super(message); }
}
