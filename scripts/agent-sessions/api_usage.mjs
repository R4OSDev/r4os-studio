/** Observe reported counters only; never modify Responses or execute tools. */
const maximum = 524288;
export function reportedUsage(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const result = {};
  for (const field of ['input_tokens', 'output_tokens', 'total_tokens']) {
    if (value[field] !== undefined) {
      if (!Number.isSafeInteger(value[field]) || value[field] < 0) return null;
      result[field] = value[field];
    }
  }
  for (const [parent, source, target] of [['input_tokens_details', 'cached_tokens', 'cached_input_tokens'],
    ['output_tokens_details', 'reasoning_tokens', 'reasoning_output_tokens']]) {
    if (value[parent]?.[source] !== undefined) {
      const count = value[parent][source];
      if (!Number.isSafeInteger(count) || count < 0) return null;
      result[target] = count;
    }
  }
  return Object.keys(result).length ? result : null;
}
export class ResponsesUsage {
  constructor(report) {
    this.report = report; this.decoder = new TextDecoder('utf-8', { fatal: true });
    this.buffer = ''; this.data = []; this.size = 0; this.failed = false; this.done = false;
  }
  push(chunk, final = false) {
    if (this.failed || this.done) return;
    try {
      this.buffer += this.decoder.decode(chunk, { stream: !final });
      while (true) {
        const index = this.buffer.search(/[\r\n]/);
        if (index < 0 || !final && this.buffer[index] === '\r' && index === this.buffer.length - 1) break;
        const line = this.buffer.slice(0, index), width = this.buffer[index] === '\r' && this.buffer[index + 1] === '\n' ? 2 : 1;
        this.buffer = this.buffer.slice(index + width);
        if (Buffer.byteLength(line) > maximum) throw Error();
        if (line === '') {
          if (this.data.length) {
            const value = JSON.parse(this.data.join('\n')); this.data = []; this.size = 0;
            if (['response.completed', 'response.incomplete'].includes(value.type)) {
              const response = value.response;
              // eslint-disable-next-line no-control-regex -- private receipt IDs cannot contain controls.
              if (typeof response?.id !== 'string' || !response.id || Buffer.byteLength(response.id) > 256 || /[\x00-\x20\x7f\ud800-\udfff]/u.test(response.id)) throw Error();
              this.done = true; this.report(response.id, reportedUsage(response.usage)); return;
            }
          }
        } else if (line.startsWith('data:')) {
          const data = line.slice(5).replace(/^ /, ''); this.size += Buffer.byteLength(data);
          if (this.size > maximum) throw Error(); this.data.push(data);
        }
      }
      if (Buffer.byteLength(this.buffer) > maximum || final && (this.buffer.length || this.data.length || !this.done)) throw Error();
    } catch { this.failed = true; this.data = []; this.buffer = ''; }
  }
}
