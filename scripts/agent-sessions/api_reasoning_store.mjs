/** Private session-owned original records. Native history holds opaque references. */
import fs from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { ChatFault } from './api_chat_fault.mjs';
import { REASONING_RECORD } from './api_reasoning.mjs';

const hash = value => createHash('sha256').update(value).digest('hex');
const MAX_RECORD = 5 * 1024 * 1024, MAX_TOTAL = 256 * 1024 * 1024, MAX_FILES = 32768;

export class ReasoningStore {
  constructor(config) {
    this.zai = config?.providerKind === 'zai-coding-plan';
    this.prefix = this.zai ? 'studio_zai_reasoning_v1:' : 'studio_openrouter_reasoning_v1:';
    if (!config || typeof config.directory !== 'string' || !config.scope || !config.origin
      || !['project','skill'].includes(config.scope.ownerType)
      || !['ownerId','sessionId','providerId','model','baseUrl','protocol'].every(key => typeof config.scope[key] === 'string' && config.scope[key])
      || !Number.isSafeInteger(config.origin.configRevision) || config.origin.configRevision < 1) this.fail();
    this.directory = config.directory; this.scope = config.scope; this.origin = config.origin;
    if (fs.realpathSync(this.directory) !== this.directory) this.fail();
    this.private(this.directory, true);
    this.bytes = 0; this.files = 0;
    for (const name of fs.readdirSync(this.directory)) {
      const item = path.join(this.directory, name); this.private(item);
      this.bytes += fs.statSync(item).size; this.files++;
    }
    if (this.bytes > MAX_TOTAL || this.files > MAX_FILES) this.fail();
  }
  fail() { throw new ChatFault(this.zai ? 'zai_reasoning_history_unavailable' : 'openrouter_reasoning_history_unavailable'); }
  private(file, directory = false) {
    const stat = fs.lstatSync(file);
    if (stat.isSymbolicLink() || (directory ? !stat.isDirectory() : !stat.isFile())
      || stat.uid !== process.geteuid() || stat.mode & 0o077 || !directory && stat.nlink !== 1) this.fail();
    return stat;
  }
  read(name) {
    const file = path.join(this.directory, name), stat = this.private(file);
    if (stat.size > MAX_RECORD) this.fail();
    const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    try {
      const opened = fs.fstatSync(fd);
      if (opened.ino !== stat.ino || opened.dev !== stat.dev) this.fail();
      return fs.readFileSync(fd);
    } finally { fs.closeSync(fd); }
  }
  write(name, value, replace = false) {
    const raw = Buffer.from(JSON.stringify(value));
    const target = path.join(this.directory, name);
    const previous = replace ? this.private(target).size : 0;
    if (raw.length > MAX_RECORD || this.bytes + raw.length - previous > MAX_TOTAL || this.files + (replace ? 0 : 1) > MAX_FILES) this.fail();
    const file = replace ? target + '.tmp-' + randomUUID() : target;
    const fd = fs.openSync(file, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
    try { fs.writeFileSync(fd, raw); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    if (replace) fs.renameSync(file, target);
    const directory = fs.openSync(this.directory, fs.constants.O_RDONLY | fs.constants.O_DIRECTORY | fs.constants.O_NOFOLLOW);
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
    this.bytes += raw.length - previous; this.files += replace ? 0 : 1;
    return hash(raw);
  }
  capture(payload, parser, assistant, state = 'complete') {
    const id = randomUUID(), name = 'response-' + id + '.json';
    const record = { schema: 1, scope: this.scope, origin: this.origin, state, nativeItemId: 'rs_studio_' + id.replaceAll('-',''),
      responseId: parser.id, providerResponseId: parser.providerId ?? null, finishReason: parser.finishReason,
      assistant, payload };
    const digest = this.write(name, record), reference = this.prefix + id + ':' + digest;
    if (state !== 'complete') return null;
    for (const call of assistant.tool_calls ?? []) {
      const index = 'call-' + hash(this.scope.model + '\n' + call.id) + '.json';
      let entries = []; const exists = fs.existsSync(path.join(this.directory,index));
      if (exists) { entries = JSON.parse(this.read(index)); if (!Array.isArray(entries) || entries.length > 256) this.fail(); }
      entries.push(reference); this.write(index, entries, exists);
    }
    return { type: 'reasoning', id: record.nativeItemId, summary: [], encrypted_content: reference };
  }
  restore(item) {
    const match = typeof item.encrypted_content === 'string' && item.encrypted_content.match(new RegExp('^' + this.prefix + '([a-f0-9-]{36}):([a-f0-9]{64})$'));
    if (!match || item.summary?.length || item.content?.length) this.fail();
    let raw, record;
    try { raw = this.read('response-' + match[1] + '.json'); record = JSON.parse(raw); } catch { this.fail(); }
    if (hash(raw) !== match[2] || record.schema !== 1 || record.state !== 'complete'
      || JSON.stringify(record.scope) !== JSON.stringify(this.scope)
      || item.id != null && item.id !== record.nativeItemId) this.fail();
    return { ...record, reference: item.encrypted_content };
  }
  verify(messages) {
    for (const message of messages) if (message.role === 'assistant') {
      const record = message[REASONING_RECORD];
      if (record) {
        const content = Array.isArray(message.content) ? message.content.map(part => part.text).join('') : message.content;
        if (content !== record.assistant.content || JSON.stringify(message.tool_calls ?? []) !== JSON.stringify(record.assistant.tool_calls ?? [])) this.fail();
      }
      for (const call of message.tool_calls ?? []) {
        const name = 'call-' + hash(this.scope.model + '\n' + call.id) + '.json';
        if (fs.existsSync(path.join(this.directory,name))) {
          let references; try { references = JSON.parse(this.read(name)); } catch { this.fail(); }
          if (!Array.isArray(references) || !references.includes(record?.reference)) this.fail();
        }
      }
    }
  }
}
