"""Bounded public deltas; readers only observe committed original events.

No transaction is held while waiting for the next delta. Non-stream events and
effect boundaries drain this buffer into the existing session transaction.
"""
import asyncio
from session_store import encode
from store import ProjectFault

MAX_EVENTS = 64
MAX_BYTES = 256 * 1024
MAX_SECONDS = .1


class PublicStream:
    def __init__(self, store):
        self.store = store
        self.events = []
        self.items = {}
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
        raw, projection = encode(payload), encode(value)
        if len(raw.encode()) > 262144 or len(projection.encode()) > 262144:
            raise ProjectFault('Agent event exceeds the output limit.')
        key = (sid, rid, value['id'])
        entry = (sid, rid, raw)
        size = len(raw.encode())
        projected = self.bytes + size + len(projection.encode()) - len(self.items.get(key, '').encode())
        if self.events and projected > MAX_BYTES:
            self.flush()
        self.events.append(entry)
        self.bytes += size + len(projection.encode()) - len(self.items.get(key, '').encode())
        self.items[key] = projection
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
            # For commit=False the caller owns the transaction, just as for
            # event(..., False). Its rollback cannot expose staged projections.
            for sid, rid, raw in self.events:
                _event(self.store, sid, rid, 'delta', raw, False)
            for (sid, rid, ident), raw in self.items.items():
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
        self.bytes = 0


def flush(store, commit=True):
    stream = getattr(store, 'public_stream', None)
    if stream:
        stream.flush(commit)


def delta(store, sid, rid, value, payload):
    if not getattr(store, 'public_stream', None):
        store.public_stream = PublicStream(store)
    store.public_stream.append(sid, rid, value, payload)
