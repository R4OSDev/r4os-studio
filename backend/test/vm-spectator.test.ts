import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { SpectatorInput, SpectatorOutput } from '../src/modules/virtual-machines/spectator.js';

const banner = Buffer.from('RFB 003.008\n');
const clientHello = Buffer.concat([banner, Buffer.from([1, 1])]);
const request = Buffer.from([3, 0, 0, 0, 0, 0, 3, 32, 2, 88]);

function fixture() {
  const input = new SpectatorInput(), output = new SpectatorOutput(input);
  const forwarded: Buffer[] = [], frames: Buffer[] = [];
  input.on('data', (data: Buffer) => forwarded.push(data)); output.on('data', (data: Buffer) => frames.push(data));
  const initialize = () => { output.write(banner); output.write(Buffer.from([1, 1])); output.write(Buffer.alloc(4)); };
  return { input, output, forwarded, frames, initialize };
}

await test('spectators negotiate a shared 3.8 None display and wait for the validated server phases', () => {
  const f = fixture();
  f.input.write(Buffer.concat([clientHello, request])); assert.equal(f.forwarded.length, 0);
  for (const byte of banner) f.output.write(Buffer.from([byte]));
  assert.deepEqual(Buffer.concat(f.forwarded), banner);
  f.output.write(Buffer.from([1])); assert.deepEqual(Buffer.concat(f.forwarded), banner);
  f.output.write(Buffer.from([1])); assert.deepEqual(Buffer.concat(f.forwarded), Buffer.concat([banner, Buffer.from([1])]));
  f.output.write(Buffer.alloc(4)); assert.deepEqual(Buffer.concat(f.forwarded), Buffer.concat([clientHello, request]));
  const pixels = Buffer.from([0, 0, 255, 4, 5, 6]); f.output.write(pixels);
  assert.deepEqual(Buffer.concat(f.frames), Buffer.concat([banner, Buffer.from([1, 1]), Buffer.alloc(4), pixels]));
  f.input.destroy(); f.output.destroy();
});

await test('fragmented/coalesced display messages preserve boundaries and strip control capability negotiation', () => {
  const f = fixture(); f.initialize();
  const values = [0, 7, -223, -239, -308, -312, -313, -23, -254, -258, -309, -316, 0xc0a1e5ce | 0, 123456];
  const encodings = Buffer.alloc(4 + values.length * 4); encodings[0] = 2; encodings.writeUInt16BE(values.length, 2);
  values.forEach((value, index) => encodings.writeInt32BE(value, 4 + index * 4));
  const pixel = Buffer.alloc(20); pixel[4] = 32; pixel[5] = 24; pixel[7] = 1;
  const continuous = Buffer.from(request); continuous[0] = 150; continuous[1] = 1;
  const fence = Buffer.from([248, 0, 0, 0, 0, 0, 0, 3, 2, 7, 8]);
  for (const byte of Buffer.concat([clientHello, pixel, encodings, request, continuous, fence])) f.input.write(Buffer.from([byte]));
  const result = f.forwarded.find((part) => part[0] === 2)!;
  assert.equal(result.readUInt16BE(2), 9);
  assert.deepEqual(Array.from({ length: 9 }, (_, index) => result.readInt32BE(4 + index * 4)), values.slice(0, 9));
  assert.deepEqual(Buffer.concat(f.forwarded.slice(-3)), Buffer.concat([request, continuous, fence]));
  f.input.destroy(); f.output.destroy();
});

for (const [name, bytes] of [
  ['keyboard', [4, 1, 0, 0, 0, 0, 0, 97]], ['pointer', [5, 1, 0, 0, 0, 0]],
  ['extended pointer', [5, 128, 0, 0, 0, 0, 1]], ['clipboard', [6, 0, 0, 0, 0, 0, 0, 1, 65]],
  ['extended clipboard', [6, 0, 0, 0, 255, 255, 255, 252, 16, 0, 0, 1]],
  ['power', [250, 0, 1, 2]], ['resize', [251, 0, 0, 1, 0, 1, 1, 0]],
  ['extended key', [255, 0, 0, 1, 0, 0, 0, 97, 0, 0, 0, 30]],
  ['unknown extension', [249, 0, 0, 0]], ['color-map mutation', [1, 0, 0, 0]],
  ['oversized encodings', [2, 0, 1, 1]], ['oversized fence', [248, 0, 0, 0, 0, 0, 0, 0, 65]],
  ['fence request', [248, 0, 0, 0, 128, 0, 0, 0, 0]],
] as const) await test(`spectators cannot forward ${name}, including subsequent coalesced bytes`, async () => {
  const f = fixture(); f.initialize(); f.input.write(clientHello);
  const failed = once(f.input, 'error');
  f.input.write(Buffer.concat([Buffer.from(bytes), request])); await failed;
  assert.deepEqual(Buffer.concat(f.forwarded), clientHello);
  f.output.destroy();
});

await test('exclusive initialization, alternate authentication and incompatible servers fail closed', async () => {
  for (const hello of [Buffer.from('RFB 003.003\n'), Buffer.concat([banner, Buffer.from([2])]), Buffer.concat([banner, Buffer.from([1, 0])])]) {
    const f = fixture(); f.initialize(); const failed = once(f.input, 'error'); f.input.write(hello); await failed;
    assert(Buffer.concat(f.forwarded).length <= 13); f.output.destroy();
  }
  for (const response of [Buffer.from('RFB 003.003\n'), Buffer.concat([banner, Buffer.from([1, 2])]), Buffer.concat([banner, Buffer.from([1, 1, 0, 0, 0, 1])])]) {
    const f = fixture(); f.input.write(Buffer.concat([clientHello, request]));
    const failed = once(f.output, 'error'); f.output.write(response); await failed;
    assert(Buffer.concat(f.forwarded).length < clientHello.length); f.input.destroy();
  }
});

await test('unconfirmed input is bounded without exposing a partial message', async () => {
  const f = fixture(), failed = once(f.input, 'error'); f.input.write(Buffer.alloc(4097)); await failed;
  assert.equal(f.forwarded.length, 0); f.output.destroy();
});
