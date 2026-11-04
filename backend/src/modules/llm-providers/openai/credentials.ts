import { open, constants } from 'node:fs/promises';
import { join } from 'node:path';

export interface NativeIdentity { accountId: string; subject: string }
export interface NativeBinding extends NativeIdentity { generation: string }

function claim(value: unknown): string {
  if (typeof value !== 'string' || !/^[\x21-\x7e]{1,512}$/.test(value)) throw new Error('Account identity unavailable.');
  return value;
}

function payload(token: unknown): Record<string, unknown> {
  if (typeof token !== 'string' || token.length > 16384) throw new Error('Account token unavailable.');
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Account token unavailable.');
  const value: unknown = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Account token unavailable.');
  return value as Record<string, unknown>;
}

/** Read only this provider's native-client file, never a browser or global cache. */
export async function nativeCredentials(home: string) {
  const file = await open(join(home, 'auth.json'), constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const before = await file.stat();
    if (!before.isFile() || before.nlink !== 1 || (before.mode & 0o777) !== 0o600
      || before.uid !== process.getuid?.() || before.gid !== process.getgid?.() || before.size > 131072) throw new Error('Private account file unavailable.');
    const value = JSON.parse(await file.readFile('utf8'));
    const after = await file.stat();
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ino !== after.ino
      || ![undefined, 'chatgpt'].includes(value.auth_mode)) throw new Error('Account changed.');
    const id = payload(value.tokens?.id_token), access = payload(value.tokens?.access_token);
    const auth = id['https://api.openai.com/auth'] as Record<string, unknown> | undefined;
    const accessAuth = access['https://api.openai.com/auth'] as Record<string, unknown> | undefined;
    const accountId = claim(value.tokens?.account_id), subject = claim(id.sub);
    if (auth?.chatgpt_account_id !== undefined && auth.chatgpt_account_id !== accountId
      || accessAuth?.chatgpt_account_id !== undefined && accessAuth.chatgpt_account_id !== accountId) throw new Error('Account changed.');
    if (typeof value.tokens.access_token !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(value.tokens.access_token)) throw new Error('Account token unavailable.');
    return { identity: { accountId, subject }, accessToken: value.tokens.access_token as string,
      expiresAt: typeof access.exp === 'number' && Number.isFinite(access.exp) ? access.exp * 1000 : null,
      // Managed edge routing needs its actual native contract before dispatch.
      managedRouting: auth?.chatgpt_account_is_fedramp === true || accessAuth?.chatgpt_account_is_fedramp === true };
  } finally { await file.close(); }
}
