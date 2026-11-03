/** Assemble provider reasoning separately from visible assistant output. */
import { ChatFault } from './api_chat_fault.mjs';
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const MAX_BYTES = 4 * 1024 * 1024, MAX_BLOCKS = 256;
export const REASONING_RECORD = Symbol('private original reasoning association');
const validText = value => typeof value === 'string' && !/[\ud800-\udfff]/u.test(value);

export class ReasoningStream {
  constructor(code = 'openrouter_reasoning_history_unavailable') { this.code = code; this.strings = {}; this.blocks = new Map(); this.size = 0; }
  fail() { throw new ChatFault(this.code); }
  push(delta) {
    for (const key of ['reasoning', 'reasoning_content']) if (delta[key] != null) {
      if (typeof delta[key] !== 'string') this.fail();
      this.strings[key] = (this.strings[key] ?? '') + delta[key];
      this.size += Buffer.byteLength(delta[key]);
    }
    if (delta.reasoning_details != null) {
      if (!Array.isArray(delta.reasoning_details) || delta.reasoning_details.length > MAX_BLOCKS) this.fail();
      for (const part of delta.reasoning_details) {
        if (!object(part) || Object.keys(part).some(key => !['type','id','format','index','text','summary','data','signature'].includes(key))) this.fail();
        if (part.index != null && (!Number.isSafeInteger(part.index) || part.index < 0 || part.index >= MAX_BLOCKS)) this.fail();
        if (part.id != null && (!validText(part.id) || !part.id.length || Buffer.byteLength(part.id) > 256)) this.fail();
        const key = part.index != null ? 'index:' + part.index : part.id != null ? 'id:' + part.id : 'anonymous:' + this.blocks.size;
        const block = this.blocks.get(key) ?? {};
        for (const field of ['type','id','format','index']) if (field in part) {
          if (block[field] != null && part[field] != null && block[field] !== part[field]) this.fail();
          if (part[field] != null || !(field in block)) block[field] = part[field];
        }
        if (!['reasoning.text','reasoning.summary','reasoning.encrypted'].includes(block.type)
          || block.format != null && (!validText(block.format) || !block.format.length || Buffer.byteLength(block.format) > 256)) this.fail();
        const content = { 'reasoning.text': 'text', 'reasoning.summary': 'summary', 'reasoning.encrypted': 'data' }[block.type];
        for (const field of ['text','summary','data','signature']) if (field in part) {
          if (field !== content && !(field === 'signature' && block.type === 'reasoning.text')) this.fail();
          const value = part[field];
          if (value !== null && typeof value !== 'string') this.fail();
          if (value !== null) { block[field] = (block[field] ?? '') + value; this.size += Buffer.byteLength(value); }
          else if (!(field in block)) block[field] = null;
        }
        this.blocks.set(key, block);
        if (this.blocks.size > MAX_BLOCKS) this.fail();
      }
    }
    if (this.size > MAX_BYTES) this.fail();
  }
  payload(final = true) {
    const result = structuredClone(this.strings);
    if (this.blocks.size) {
      const blocks = [...this.blocks.values()];
      if (blocks.every(value => Number.isSafeInteger(value.index))) blocks.sort((a,b) => a.index - b.index);
      result.reasoning_details = structuredClone(blocks);
    }
    if (final) {
      for (const value of Object.values(this.strings)) if (!validText(value)) this.fail();
      for (const block of this.blocks.values()) for (const field of ['text','summary','data','signature']) {
        if (block[field] != null && !validText(block[field])) this.fail();
      }
      for (const block of this.blocks.values()) {
        const field = { 'reasoning.text':'text','reasoning.summary':'summary','reasoning.encrypted':'data' }[block.type];
        if (!validText(block[field])) this.fail();
      }
    }
    if (Buffer.byteLength(JSON.stringify(result)) > MAX_BYTES) this.fail();
    return result;
  }
  get present() { return Object.keys(this.strings).length > 0 || this.blocks.size > 0; }
}
