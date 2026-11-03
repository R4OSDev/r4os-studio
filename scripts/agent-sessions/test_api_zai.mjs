import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { zaiHeaders } from './api_zai.mjs';

test('the verified stable OpenCode branch sets only its actual Z.AI identity and affinity headers', () => {
  const profile = JSON.parse(readFileSync(new URL('../../shared/zai-client.json', import.meta.url)));
  const sessionId = 'ses_' + 'a'.repeat(64), headers = zaiHeaders({ ...profile, sessionId });
  assert.deepEqual(headers, { 'User-Agent': 'opencode/1.19.5', 'x-opencode-session-id': sessionId,
    'x-session-affinity': sessionId, 'X-Session-Id': sessionId });
  assert.equal(JSON.stringify(headers).includes('Studio'), false);
  assert.equal(headers['x-opencode-client'], undefined);
  assert.throws(() => zaiHeaders({ ...profile, sessionId, userAgent: 'opencode/1.19.5\r\nX-Key: value' }));
  assert.throws(() => zaiHeaders({ ...profile, sessionId: '../foreign' }));
  assert.throws(() => zaiHeaders({ ...profile, sessionId, referenceCommit: 'not verified' }));
});
