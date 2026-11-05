import type { SessionItem } from '../../../../shared/agent-sessions';

export type TextDelta = { runId: string; itemId: string; field: 'text' | 'output'; text: string; live: boolean };
const key = (runId: string, itemId: string) => runId + ':' + itemId;
const indexes = new WeakMap<SessionItem[], Map<string, number>>();

// Immutable snapshots retain every unchanged item. Indexes belong to that exact
// snapshot; replacing history or prepending an older page cannot reuse old offsets.
export function applyDeltas(items: SessionItem[], deltas: TextDelta[]) {
  let index = indexes.get(items);
  if (!index) { index = new Map(items.map((item, offset) => [key(item.runId, item.id), offset])); indexes.set(items, index); }
  const additions = new Map<number, { text: string[]; output: string[] }>();
  for (const delta of deltas) {
    const offset = index.get(key(delta.runId, delta.itemId));
    if (offset === undefined) continue;
    let value = additions.get(offset);
    if (!value) { value = { text: [], output: [] }; additions.set(offset, value); }
    value[delta.field].push(delta.text);
  }
  if (!additions.size) return items;
  const next = items.slice();
  for (const [offset, value] of additions) {
    const item = { ...items[offset] };
    if (value.text.length) item.text = (item.text ?? '') + value.text.join('');
    if (value.output.length) item.output = (item.output ?? '') + value.output.join('');
    next[offset] = item;
  }
  indexes.set(next, index);
  return next;
}

// This holds only already durable UI deltas. A frame usually drains it; the
// timer and bounds also drain background tabs without retaining an endless tail.
export class SessionDeltas {
  private values: TextDelta[] = [];
  private bytes = 0;
  private frame: number | undefined;
  private timer: number | undefined;
  constructor(private readonly apply: (values: TextDelta[]) => void) {}
  push(delta: TextDelta) {
    this.values.push(delta); this.bytes += delta.text.length * 2;
    if (this.values.length >= 128 || this.bytes >= 256 * 1024) { this.flush(); return; }
    if (this.frame === undefined) {
      this.frame = requestAnimationFrame(() => this.flush());
      this.timer = window.setTimeout(() => this.flush(), 50);
    }
  }
  flush = () => {
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    window.clearTimeout(this.timer); this.frame = this.timer = undefined;
    const values = this.values;
    this.values = []; this.bytes = 0;
    if (values.length) this.apply(values);
  };
  clear() {
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    window.clearTimeout(this.timer); this.frame = this.timer = undefined;
    this.values = []; this.bytes = 0;
  }
}
