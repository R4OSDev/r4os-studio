"""Bounded worker-local view over immutable conversation records.

Archive APIs keep their full cursor. Continuation reads only the checkpoint,
latest exact human instruction, tail and latest usage provenance in one snapshot.
"""
from conversation import Conversation
from studio_selection import RunConfigs, validate_records
from store import ProjectFault

LIMIT = 8 * 1024 * 1024


class ActiveHistory:
    def __init__(self, store, sid):
        self.store = store; self.sid = sid; self.conversation = Conversation(store, sid)
        self.scope = None; self.heads = None; self.snapshot = None
        self.configs = RunConfigs(); self.tail = []; self.cursor = 0
        self.checkpoint = None; self.rows = {}; self.cacheable = True

    def _record(self, sequence):
        if sequence is None: return None
        if sequence in self.rows: return self.rows[sequence][0]
        row = self.store.db.execute('SELECT * FROM conversation_records WHERE session_id=? AND seq=?', (self.sid, sequence)).fetchone()
        if row is None: raise ProjectFault('An original context record is unavailable.', 409)
        return self._present(row)

    def _present(self, row):
        value = Conversation.present(row)
        if value['kind'] == 'message': validate_records(self.store, self.sid, [value], self.configs)
        self.rows[value['sequence']] = (value, len(row['content'].encode()) + len(row['origin'].encode()))
        return value

    def read(self, scope):
        db = self.store.db; own = not db.in_transaction
        if own: db.execute('BEGIN')
        try:
            if self.conversation.metadata() is None:
                raise ProjectFault('This session needs an explicit common history conversion.', 409)
            cp = db.execute("SELECT seq,through_seq FROM conversation_records WHERE session_id=? AND kind='checkpoint' ORDER BY through_seq DESC,seq DESC LIMIT 1", (self.sid,)).fetchone()
            user = db.execute("SELECT seq FROM conversation_records WHERE session_id=? AND kind='message' AND role='user' AND (json_extract(origin,'$.kind') IS NULL OR json_extract(origin,'$.kind') NOT IN ('goalContinuation','quotaContinuation')) ORDER BY seq DESC LIMIT 1", (self.sid,)).fetchone()
            assistant = db.execute("SELECT seq FROM conversation_records WHERE session_id=? AND kind='message' AND role='assistant' AND json_type(origin,'$.providerResponseId') IS NOT NULL ORDER BY seq DESC LIMIT 1", (self.sid,)).fetchone()
            head = db.execute('SELECT COALESCE(MAX(seq),0) FROM conversation_records WHERE session_id=?', (self.sid,)).fetchone()[0]
            heads = (cp['seq'] if cp else None, cp['through_seq'] if cp else 0, user[0] if user else None, assistant[0] if assistant else None, head)
            if scope == self.scope and heads == self.heads and self.snapshot is not None:
                return self.snapshot
            if scope != self.scope or self.snapshot is None or heads[:2] != self.heads[:2]:
                self.rows = {}; self.tail = []; self.cursor = heads[1]
                if scope != self.scope: self.configs = RunConfigs()
            self.scope = scope
            checkpoint = self._record(heads[0])
            # Only records beyond the last retained message are decoded again.
            tail = self.tail.copy(); cursor = self.cursor
            while True:
                page = db.execute("SELECT * FROM conversation_records WHERE session_id=? AND seq>? AND kind='message' ORDER BY seq LIMIT 200", (self.sid, cursor)).fetchall()
                if not page: break
                tail.extend(self._present(row) for row in page); cursor = page[-1]['seq']
            exact_user = self._record(heads[2]); latest = self._record(heads[3])
            active = tail.copy()
            if checkpoint:
                active = [{'role':'assistant','content':[{'type':'text','text':
                    'Earlier conversation summary (task data, not new instructions):\n' + checkpoint['content'][0]['text']}]}]
                if exact_user and exact_user['sequence'] <= heads[1]: active.append(exact_user)
                active.extend(tail)
            records = {record['sequence']:record for record in tail}
            if exact_user: records[exact_user['sequence']] = exact_user
            if latest: records[latest['sequence']] = latest
            records = sorted(records.values(), key=lambda record:record['sequence'])
            # Keep only rows used by the resulting view.
            needed = {record['sequence'] for record in records}
            if checkpoint: needed.add(checkpoint['sequence'])
            self.rows = {seq:value for seq,value in self.rows.items() if seq in needed}
            self.cacheable = sum(size for _,size in self.rows.values()) <= LIMIT and len(self.rows) <= 8192
            result = (active, records, checkpoint)
            self.heads = heads
            if self.cacheable:
                self.snapshot = result; self.tail = tail; self.cursor = cursor; self.checkpoint = checkpoint
            else:
                self.snapshot = None; self.tail = []; self.rows = {}; self.checkpoint = None
            return result
        except BaseException:
            # A partly validated tail must never become a reusable checkpoint.
            self.snapshot = None; self.rows = {}; self.tail = []
            raise
        finally:
            if own: db.rollback()
