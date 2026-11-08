"""Bounded public deltas; readers only observe committed original events.

No transaction is held while waiting for the next delta. Non-stream events and
effect boundaries drain this buffer into the existing session transaction.
"""
import asyncio
from copy import deepcopy
from session_store import encode
from text_budget import content_bytes
from store import ProjectFault

MAX_EVENTS = 64
MAX_BYTES = 256 * 1024
MAX_SECONDS = .1


class PublicStream:
    def __init__(self, store):
        self.store = store
        self.events = []
        self.items = {}
        self.sizes = {}
        self.bytes = 0
        self.timer = None
        self.failure = None

    def check(self):
        if self.failure:
            raise ProjectFault('Public stream storage is unconfirmed. Original receipts were preserved.', 503) from self.failure

    def expired(self):
        self.timer = None
        try:
            self.flush()
        except Exception as error:
            # Never retry an uncertain commit or confirm a tool after it.
            self.failure = error
            failed = getattr(self.store, 'public_stream_failed', None)
            if failed:
                failed()

    def append(self, sid, rid, value, payload):
        self.check()
        raw = encode(payload)
        key = (sid, rid, value['id'])
        field = payload.get('field','text'); text = value.get(field); added = payload.get('text')
        previous = self.items.get(key); prior_size, prior_field, prior_content = self.sizes.get(key,(0,None,0))
        if isinstance(text,str):
            old = previous.get(field) if previous else None
            if (prior_field == field and isinstance(old,str) and isinstance(added,str)
                    and len(text) == len(old) + len(added) and text.startswith(old) and text.endswith(added)):
                content = prior_content + content_bytes(added)
            else: content = content_bytes(text)
            projection_size = len(encode({**value,field:''}).encode()) + content
        else:
            projection_size = len(encode(value).encode()); field = None; content = 0
        size = len(raw.encode())
        if size > 262144 or projection_size > 262144:
            raise ProjectFault('Agent event exceeds the output limit.')
        projection = deepcopy(value)
        entry = (sid, rid, raw)
        projected = self.bytes + size + projection_size - prior_size
        if self.events and projected > MAX_BYTES:
            self.flush()
        self.events.append(entry)
        self.bytes += size + projection_size - self.sizes.get(key,(0,None,0))[0]
        self.items[key] = projection
        self.sizes[key] = projection_size, field, content
        if len(self.events) >= MAX_EVENTS or self.bytes >= MAX_BYTES:
            self.flush()
        elif self.timer is None:
            try:
                self.timer = asyncio.get_running_loop().call_later(MAX_SECONDS, self.expired)
            except RuntimeError:
                self.flush()  # Synchronous callers cannot promise a timed drain.

    def flush(self, commit=True):
        self.check()
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if not self.events:
            return
        from run_store import _event
        db = self.store.db
        try:
            projections = {}
            for key, value in self.items.items():
                raw = encode(value)
                if len(raw.encode()) != self.sizes[key][0] or len(raw.encode()) > 262144:
                    raise ProjectFault('Agent projection exceeds its original stream budget.')
                projections[key] = raw
            # For commit=False the caller owns the transaction, just as for
            # event(..., False). Its rollback cannot expose staged projections.
            for sid, rid, raw in self.events:
                _event(self.store, sid, rid, 'delta', raw, False)
            for (sid, rid, ident), raw in projections.items():
                db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                           (sid, rid, ident, raw))
            if commit:
                db.commit()
        except Exception as error:
            self.failure = error
            if commit:
                db.rollback()
            raise
        self.events.clear()
        self.items.clear()
        self.sizes.clear()
        self.bytes = 0


def flush(store, commit=True):
    stream = getattr(store, 'public_stream', None)
    if stream:
        stream.flush(commit)


def delta(store, sid, rid, value, payload):
    if not getattr(store, 'public_stream', None):
        store.public_stream = PublicStream(store)
    store.public_stream.append(sid, rid, value, payload)
