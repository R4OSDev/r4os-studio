import { Transform, type TransformCallback } from 'node:stream';

// Only framebuffer encodings and display notifications. Do not negotiate
// clipboard, power, extended keyboard/mouse or other client-control extensions.
const displayEncodings = new Set([0, 1, 2, 5, 6, 7, 16, 21, 50, -260,
  -223, -224, -239, -261, -307, -308, -312, -313, 0x574d5664]);
const banner = Buffer.from('RFB 003.008\n');
type Stage = 'version' | 'security' | 'shared' | 'messages';
const stages: Stage[] = ['version', 'security', 'shared', 'messages'];

/** Fail-closed client half of our private QEMU RFB 3.8 / None connection.
 * WebSocket frames are not RFB message boundaries. Never forward a partial
 * message, an exclusive ClientInit, or an unrecognized extension to QEMU.
 */
export class SpectatorInput extends Transform {
  private pending = Buffer.alloc(0);
  private stage: Stage = 'version';
  private allowed = -1;
  constructor() { super({ highWaterMark: 64 * 1024 }); }

  confirm(stage: Stage) {
    this.allowed = stages.indexOf(stage);
    try { this.drain(); } catch (error) { this.destroy(error as Error); }
  }

  override _transform(chunk: Buffer, _encoding: BufferEncoding, done: TransformCallback) {
    try {
      this.pending = Buffer.concat([this.pending, chunk]);
      this.drain();
      // Bounds incomplete messages and clients that pipeline before the server
      // confirms the version, None security and successful initialization.
      if (this.pending.length > 4096) throw new Error('Spectator handshake or message is too large.');
      done();
    } catch (error) { done(error as Error); }
  }

  private drain() {
    while (this.pending.length && stages.indexOf(this.stage) <= this.allowed && !this.destroyed) {
      let length: number;
      if (this.stage === 'version') length = 12;
      else if (this.stage === 'security' || this.stage === 'shared') length = 1;
      else {
        switch (this.pending[0]) {
          case 0: length = 20; break; // SetPixelFormat
          case 2: // SetEncodings
            if (this.pending.length < 4) return;
            if (this.pending.readUInt16BE(2) > 256) throw new Error('Too many display encodings.');
            length = 4 + this.pending.readUInt16BE(2) * 4; break;
          case 3: case 150: length = 10; break; // Framebuffer request / continuous updates
          case 248: // Fence replies; bounded by the RFB extension specification.
            if (this.pending.length < 9) return;
            if (this.pending[8] > 64 || (this.pending.readUInt32BE(4) & 0x80000000)) throw new Error('Invalid display fence.');
            length = 9 + this.pending[8]; break;
          default: throw new Error('Guest input is disabled in spectator mode.');
        }
      }
      if (this.pending.length < length) return;
      let message = this.pending.subarray(0, length);
      if (this.stage === 'version') {
        if (!message.equals(banner)) throw new Error('Unsupported spectator protocol.');
        this.stage = 'security';
      } else if (this.stage === 'security' || this.stage === 'shared') {
        if (message[0] !== 1) throw new Error('Spectators require a shared private display.');
        this.stage = this.stage === 'security' ? 'shared' : 'messages';
      } else if (message[0] === 2) {
        const encodings: number[] = [];
        for (let offset = 4; offset < length; offset += 4) {
          const value = message.readInt32BE(offset);
          if (displayEncodings.has(value) || (value >= -32 && value <= -23) || (value >= -256 && value <= -247)) encodings.push(value);
        }
        message = Buffer.alloc(4 + encodings.length * 4); message[0] = 2; message.writeUInt16BE(encodings.length, 2);
        encodings.forEach((value, index) => message.writeInt32BE(value, 4 + index * 4));
      }
      this.push(message);
      this.pending = this.pending.subarray(length);
    }
  }
}

/** Validate the private server handshake before allowing each client phase.
 * A future authentication/protocol change fails closed rather than shifting
 * the input parser's message boundaries. Pixel data remains an opaque stream.
 */
export class SpectatorOutput extends Transform {
  private pending = Buffer.alloc(0);
  private stage: Stage = 'version';
  constructor(private input: SpectatorInput) { super({ highWaterMark: 64 * 1024 }); }
  override _transform(chunk: Buffer, _encoding: BufferEncoding, done: TransformCallback) {
    try {
      if (this.stage === 'messages') { this.push(chunk); done(); return; }
      this.pending = Buffer.concat([this.pending, chunk]);
      while (this.pending.length) {
        let length: number, next: Stage;
        if (this.stage === 'version') { length = 12; next = 'security'; }
        else if (this.stage === 'security') { length = 2; next = 'shared'; }
        else { length = 4; next = 'messages'; }
        if (this.pending.length < length) break;
        const message = this.pending.subarray(0, length);
        if ((this.stage === 'version' && !message.equals(banner))
          || (this.stage === 'security' && !message.equals(Buffer.from([1, 1])))
          || (this.stage === 'shared' && message.readUInt32BE() !== 0)) throw new Error('Unsupported private spectator handshake.');
        this.push(message); this.input.confirm(this.stage);
        this.pending = this.pending.subarray(length); this.stage = next;
        if (next === 'messages') {
          if (this.pending.length) this.push(this.pending);
          this.pending = Buffer.alloc(0); this.input.confirm('messages'); break;
        }
      }
      done();
    } catch (error) { done(error as Error); }
  }
}
