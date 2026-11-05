import type { AgentEvent } from '../../../../shared/agent-sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';

export type EventPage = { events: AgentEvent[]; watermark?: number; hasMore: boolean; nextPollAt: number };
type SavedPage = { after: number; through?: number; page: EventPage; bytes: number };
const interval = 300, maxBytes = 2 * 1024 * 1024;

/** One bounded read/cache path per typed owner/session; SQLite stays authoritative. */
export class EventReader {
  references = 0;
  private closed = false;
  private pages: SavedPage[] = [];
  private bytes = 0;
  private pending = new Map<string, Promise<EventPage>>();
  private chain: Promise<unknown> = Promise.resolve();
  constructor(private payload: Record<string, unknown>) {}

  private cached(after: number, through?: number): EventPage | undefined {
    const now = Date.now();
    for (const { after: start, through: savedThrough, page } of this.pages) {
      const last = page.events.at(-1)?.seq ?? start;
      if (page.nextPollAt <= now || after < start || (through === undefined && savedThrough !== undefined) || (page.hasMore && after >= last)
          || (through !== undefined && page.watermark !== undefined && page.watermark < through)) continue;
      const watermark = through === undefined ? page.watermark : Math.min(through, page.watermark ?? through);
      const events = page.events.filter(event => event.seq > after && (watermark === undefined || event.seq <= watermark));
      return { events, watermark, hasMore: watermark === undefined ? page.hasMore : (events.at(-1)?.seq ?? after) < watermark,
        nextPollAt: page.nextPollAt };
    }
  }

  read(after: number, through?: number): Promise<EventPage> {
    if (this.closed) return Promise.reject(new ProjectError('The session stream closed.', 503));
    const cached = this.cached(after, through);
    if (cached) return Promise.resolve(cached);
    const key = `${after}:${through ?? ''}`, pending = this.pending.get(key);
    if (pending) return pending;
    if (this.pending.size >= 32) return Promise.reject(new ProjectError('Session stream reads are busy.', 429));
    const work = this.chain.then(async () => {
      if (this.closed) throw new ProjectError('The session stream closed.', 503);
      const reused = this.cached(after, through);
      if (reused) return reused;
      const result = await agentHost<{ events: AgentEvent[]; watermark?: number; hasMore?: boolean }>({
        ...this.payload, after, eventPage: 1, ...(through === undefined ? {} : { through }),
      });
      if (this.closed) throw new ProjectError('The session stream closed.', 503);
      const page = { events: result.events, watermark: result.watermark,
        hasMore: result.hasMore ?? result.events.length > 0, nextPollAt: Date.now() + interval };
      const bytes = Buffer.byteLength(JSON.stringify(page));
      if (bytes <= maxBytes) {
        this.pages.unshift({ after, through, page, bytes }); this.bytes += bytes;
        while (this.pages.length > 8 || this.bytes > maxBytes) this.bytes -= this.pages.pop()!.bytes;
      }
      return page;
    });
    this.chain = work.catch(() => {});
    const observed = work.finally(() => { this.pending.delete(key); });
    this.pending.set(key, observed);
    return observed;
  }

  close() { this.closed = true; this.pages = []; this.bytes = 0; }
}

export class SessionStreams {
  private readers = new Map<string, EventReader>();
  acquire(payload: Record<string, unknown>) {
    const key = JSON.stringify([payload.ownerType ?? 'project', payload.ownerId ?? payload.projectId, payload.sessionId]);
    let reader = this.readers.get(key);
    if (!reader) { reader = new EventReader(payload); this.readers.set(key, reader); }
    reader.references++;
    let released = false;
    return { reader, release: () => {
      if (released) return;
      released = true;
      if (--reader.references === 0) { reader.close(); this.readers.delete(key); }
    } };
  }
}
