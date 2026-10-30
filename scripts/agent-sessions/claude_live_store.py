"""Original ordinary-worker control identity, separate from its frozen config."""
import json
import os

from attachment_store import birth
from claude_goal import digest
from session_store import encode
from store import ProjectFault


def exists(store):
    return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_live_workers'").fetchone())


def binding(worker):
    return {'owner':{'type':worker.store.owner_type,'id':worker.store.owner_id},'sessionId':worker.session_id,
        'runId':worker.run_id,'requestId':worker.row['request_id'],'configSha256':digest(worker.config),
        'worker':worker.credential_worker,'nativeSessionId':worker.config['engine']['claude']['nativeSessionId']}


def open_source(worker):
    value=binding(worker)
    if (worker.config.get('claudeGoalPreparation') is not True or worker.config.get('claudeGoalExecution')
        or not worker.sent or worker.stopping or value['worker']['pid']!=os.getpid()):
        raise ProjectFault('The original ordinary Claude input cannot open live control.',409)
    with worker.store.db:
        worker.store.db.execute('CREATE TABLE IF NOT EXISTS claude_live_workers(run_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),binding TEXT NOT NULL,state TEXT NOT NULL,activation TEXT)')
        old=worker.store.db.execute('SELECT * FROM claude_live_workers WHERE run_id=?',(worker.run_id,)).fetchone()
        if old:
            if json.loads(old['binding'])!=value or old['state']!='open':raise ProjectFault('The original Claude control was already closed or activated.',409)
            return
        worker.store.db.execute('INSERT INTO claude_live_workers VALUES (?,?,?,\'open\',NULL)',(worker.run_id,worker.session_id,encode(value)))


def target(store,sid,run):
    row=store.db.execute('SELECT * FROM claude_live_workers WHERE run_id=? AND session_id=?',(run['id'],sid)).fetchone() if exists(store) else None
    config=json.loads(run['config']);meta=json.loads(run['worker'] or '{}')
    if (not row or row['state']!='open' or row['activation'] is not None or not run['busy'] or run['state']!='running'
        or config.get('claudeGoalPreparation') is not True or config.get('claudeGoalExecution')
        or config['engine'].get('kind')!='claude-code' or type(meta.get('pid')) is not int
        or birth(meta['pid'])!=meta.get('birth') or not meta.get('release')):
        raise ProjectFault('The original Claude response is not ready for live Goal control.',409)
    expected={'owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,'runId':run['id'],
        'requestId':run['request_id'],'configSha256':digest(config),'worker':meta,
        'nativeSessionId':json.loads(store.row(sid)['engine'])['claude']['nativeSessionId']}
    if json.loads(row['binding'])!=expected:raise ProjectFault('The original Claude live worker binding changed.',409)
    return expected


def supported(store,run):
    try:target(store,run['session_id'],run);return True
    except (ProjectFault,KeyError,TypeError,ValueError,OSError):return False


def mark(worker,state,activation=None):
    if state not in ('waiting','goal','closed'):raise ValueError('Invalid live control state.')
    with worker.store.db:
        row=worker.store.db.execute('SELECT binding FROM claude_live_workers WHERE run_id=?',(worker.run_id,)).fetchone()
        if not row or json.loads(row[0])!=binding(worker):raise ProjectFault('The original Claude live control record changed.',409)
        worker.store.db.execute('UPDATE claude_live_workers SET state=?,activation=COALESCE(?,activation) WHERE run_id=?',(state,activation,worker.run_id))


def active_spec(store,run_id):
    from claude_goal import exists as executions
    if not executions(store):return None
    rows=store.db.execute('SELECT payload FROM claude_goal_executions WHERE run_id=? ORDER BY rowid DESC',(run_id,))
    for row in rows:
        value=json.loads(row[0])
        if value['contract'].get('liveTarget') and value.get('controlOpen') is True:return value['contract']
    return None


def close_source(worker):
    if not exists(worker.store):return
    with worker.store.db:worker.store.db.execute("UPDATE claude_live_workers SET state='closed' WHERE run_id=?",(worker.run_id,))


def live_plays(store,run_id):
    spec=active_spec(store,run_id)
    return {spec['requestId']} if spec else set()
