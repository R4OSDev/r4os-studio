import test from 'node:test';
import assert from 'node:assert/strict';
import { updateActions } from '../../frontend/src/features/projects/UpdateRecord.js';
import type { UpdateInstallation } from '../../shared/update-packages.js';

await test('native update actions keep awaiting commit, unknown and rollback outcomes distinct', () => {
  const record = { id: 'update', phase: 'awaiting_commit', batchId: '9007199254740993', transactions: [] } as unknown as UpdateInstallation;
  assert.deepEqual(updateActions(record), ['verify', 'commit', 'abort-batch', 'resume-batch']);
  assert.deepEqual(updateActions({ ...record, phase: 'install_unconfirmed' }), ['verify', 'resume-batch']);
  assert.deepEqual(updateActions({ ...record, phase: 'installed', installationConfirmed: true }), ['verify', 'rollback-last', 'cleanup']);
  assert.deepEqual(updateActions({ ...record, phase: 'rolled_back', rollbackConfirmed: true }), ['verify', 'cleanup']);
  assert.deepEqual(updateActions({ ...record, phase: 'aborted', abortConfirmed: true, cleanupConfirmed: true }), ['verify']);
  const live = { ...record, phase: 'install_unconfirmed', batchId: undefined, transactions: ['18446744073709551615'] };
  assert.deepEqual(updateActions(live), ['verify', 'resume']);
});
