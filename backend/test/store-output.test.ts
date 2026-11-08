import test from 'node:test';
import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { projectStore } from '../src/modules/projects/store.js';
import { skillStore } from '../src/modules/skills/store.js';

await test('project and skill responses preserve every UTF-8 split and reject incomplete or oversized JSON', async (t) => {
  let child: EventEmitter & { stdin: PassThrough; stdout: PassThrough; kill: () => boolean };
  t.mock.method(childProcess, 'spawn', () => {
    child = Object.assign(new EventEmitter(), { stdin: new PassThrough(), stdout: new PassThrough(), kill: () => true });
    return child;
  });
  syncBuiltinESMExports();
  try {
    const expected = { name: 'ä€🦀 e\u0301', text: '/workspace/文書' };
    const raw = Buffer.from(JSON.stringify({ result: expected }));
    for (const read of [() => projectStore('/own-fixture', {}), () => skillStore('/own-fixture', {})]) {
      for (let cut = 1; cut < raw.length; cut++) {
        const result = read();
        child!.stdout.emit('data', raw.subarray(0, cut)); child!.stdout.emit('data', raw.subarray(cut));
        child!.emit('close', 0);
        assert.deepEqual(await result, expected);
      }
      for (const invalid of [Buffer.from('{"result":'), Buffer.from('{broken}'), Buffer.from('ä'.repeat(1024 * 1024 + 1))]) {
        const result = read();
        const rejected = assert.rejects(result);
        child!.stdout.emit('data', invalid); child!.emit('close', 1);
        await rejected;
      }
    }
  } finally { t.mock.restoreAll(); syncBuiltinESMExports(); }
});
