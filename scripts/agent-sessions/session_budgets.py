"""Transactional counters over original session data, including older writers.

Each source is inventoried once, in the same write transaction that installs
its triggers. The triggers also charge old pinned workers and SQL deletion.
Events retain their historical character unit; conversation/raw budgets use
UTF-8 bytes. No original content or quota is changed.
"""
from store import ProjectFault


SOURCES = {
    'events': ('events', 'length({row}.payload)', '{row}.session_id'),
    'conversation': ('conversation_records',
                     'length(CAST({row}.content AS BLOB))+length(CAST({row}.origin AS BLOB))', '{row}.session_id'),
    'raw': ('studio_model_events', 'length(CAST({row}.raw AS BLOB))',
            '(SELECT session_id FROM session_budget_runs WHERE run_id={row}.run_id)'),
}


def trigger_sql(kind):
    table, charge, scope = SOURCES[kind]
    prefix = 'session_budget_' + kind
    old, new = scope.format(row='OLD'), scope.format(row='NEW')
    add = ("INSERT INTO session_byte_budgets(session_id,budget,used) VALUES (" + new + ", '" + kind + "', "
           + charge.format(row='NEW') + ") ON CONFLICT(session_id,budget) DO UPDATE SET used=used+excluded.used;")
    remove = ("UPDATE session_byte_budgets SET used=used-(" + charge.format(row='OLD')
              + ") WHERE session_id=" + old + " AND budget='" + kind + "';")
    result = {
        prefix + '_insert': f'AFTER INSERT ON {table} BEGIN {add} END',
        prefix + '_delete': f'AFTER DELETE ON {table} BEGIN {remove} END',
        prefix + '_update': f'AFTER UPDATE ON {table} BEGIN {remove} {add} END',
        prefix + '_session': ("AFTER INSERT ON sessions BEGIN INSERT INTO session_byte_budgets VALUES "
                             "(NEW.id, '" + kind + "', 0); END"),
    }
    if kind == 'raw':
        # Keep this mapping until session deletion, even if a run is deleted
        # before its deferred/cascading raw children. It contains no payloads.
        for action in ('INSERT', 'UPDATE'):
            result[prefix + '_bind_' + action.lower()] = (
                f'BEFORE {action} ON {table} BEGIN INSERT OR IGNORE INTO session_budget_runs '
                'SELECT NEW.run_id,session_id FROM runs WHERE id=NEW.run_id; END')
    return result


def initialize(db, kind):
    db.execute('''CREATE TABLE IF NOT EXISTS session_byte_budgets(
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        budget TEXT NOT NULL,used INTEGER NOT NULL CHECK(typeof(used)='integer' AND used>=0),
        PRIMARY KEY(session_id,budget))''')
    db.execute('CREATE TABLE IF NOT EXISTS session_budget_formats(budget TEXT PRIMARY KEY,format INTEGER NOT NULL)')
    row = db.execute('SELECT format FROM session_budget_formats WHERE budget=?', (kind,)).fetchone()
    definitions = trigger_sql(kind)
    if row:
        if row[0] != 1:
            raise ProjectFault('The original session budget format is unavailable.', 503)
        count = db.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\'trigger\' AND name IN ('
                           + ','.join('?' for _ in definitions) + ')', tuple(definitions)).fetchone()[0]
        if count != len(definitions):
            raise ProjectFault('The original session budget accounting is incomplete.', 503)
        return
    if db.execute('SELECT 1 FROM session_byte_budgets WHERE budget=? LIMIT 1', (kind,)).fetchone():
        raise ProjectFault('The original session budget initialization is unconfirmed.', 503)
    table, charge, scope = SOURCES[kind]
    if kind == 'raw':
        db.execute('''CREATE TABLE IF NOT EXISTS session_budget_runs(
            run_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE)''')
        db.execute('''INSERT OR IGNORE INTO session_budget_runs SELECT id,session_id FROM runs
            WHERE id IN (SELECT DISTINCT run_id FROM studio_model_events)''')
    # Zero rows for every existing session, and a creation trigger for every
    # future one, make a missing counter an error rather than free capacity.
    db.execute('INSERT INTO session_byte_budgets SELECT id,?,0 FROM sessions', (kind,))
    db.execute('INSERT INTO session_byte_budgets SELECT ' + scope.format(row='source') + ',?,SUM('
               + charge.format(row='source') + ') FROM ' + table + ' source GROUP BY '
               + scope.format(row='source') + ' ON CONFLICT(session_id,budget) DO UPDATE SET used=excluded.used', (kind,))
    for name, sql in definitions.items():
        db.execute('CREATE TRIGGER "' + name + '" ' + sql)
    db.execute('INSERT INTO session_budget_formats VALUES (?,1)', (kind,))


def total(db, session_id, kind):
    if kind not in SOURCES:
        raise ValueError('Unknown session budget.')
    # A normal deferred read must not race a writer between quota check and
    # insertion. Do not use executescript: it would commit the caller's work.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    initialize(db, kind)
    row = db.execute('SELECT used FROM session_byte_budgets WHERE session_id=? AND budget=?',
                     (session_id, kind)).fetchone()
    if row is None or type(row[0]) is not int or row[0] < 0:
        raise ProjectFault('The original session budget is unavailable. History was preserved.', 503)
    return row[0]
