"""Read-only, bounded project-list activity. No recovery, histories or native RPC."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import stat

from attachment_store import birth
from owner import binding
from session_store import identity, now
from store import ProjectFault

UNIT = 'r4os-studio-agent@{}.service'


def connect(path):
    if (path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_nlink != 1): raise ValueError('Invalid activity source.')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)
    db.row_factory = sqlite3.Row
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError('Unsupported activity source.')
        db.execute('PRAGMA query_only=ON')
        return db
    except Exception:
        db.close(); raise


async def units(names):
    if not names: return {}
    process = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', 'show',
        '--property=Id,ActiveState,MainPID', '--', *names,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        raw, _ = await asyncio.wait_for(process.communicate(), 2)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        process.kill(); await process.communicate(); raise
    if process.returncode or len(raw) > 65536: raise ValueError('Activity units unavailable.')
    result = {}
    for block in raw.decode().strip().split('\n\n'):
        value = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        if value.get('Id') in names: result[value['Id']] = value
    return result


def executing(db, row, tables):
    if not row['busy'] or row['state'] not in ('starting', 'running', 'stopping'): return False
    if row['state'] in ('starting', 'stopping'): return True
    live = 'goal_activations' in tables and db.execute(
        "SELECT 1 FROM goal_activations WHERE run_id=? AND session_id=? AND state='confirmed' LIMIT 1",
        (row['id'], row['session_id'])).fetchone() is not None
    if not row['goal_execution'] and not live: return True
    # A paused/stopped Goal with an idle worker is not ongoing execution. A
    # still-running turn (including its final cleanup) remains real activity.
    if 'goal_turns' in tables and db.execute(
            "SELECT 1 FROM goal_turns WHERE run_id=? AND status='running' LIMIT 1", (row['id'],)).fetchone(): return True
    if 'session_goals' not in tables: return False
    goal = db.execute("SELECT phase,json_extract(native,'$.status') AS status FROM session_goals WHERE session_id=? AND run_id=?",
        (row['session_id'], row['id'])).fetchone()
    return bool(goal and goal['phase'] != 'unknown' and goal['status'] == 'active')


async def snapshot(host, read_units=units):
    root = Path(host.config['projects']).absolute()
    try:
        with closing(connect(root / 'Projects.sqlite')) as db:
            registered = {identity(row[0]) for row in db.execute("SELECT id FROM projects WHERE state='ready'")}
        grouped = {}
        # Coordinator admission/recovery already owns these bindings. Revalidate
        # their original private records; never discover sessions or past runs.
        for run_id, known in list(host.active.items())[:128]:
            try:
                kind, project = binding(known)
                if kind != 'project' or project not in registered: continue
                path = host.root / identity(run_id) / 'worker.json'
                if path.stat().st_size > 65536: continue
                meta = host.metadata(path)
                if (meta != known or binding(meta) != (kind, project) or meta['runId'] != run_id): continue
                grouped.setdefault(project, []).append(meta)
            except (OSError, ValueError, KeyError, TypeError, ProjectFault): continue
        candidates = []
        for project, records in grouped.items():
            try:
                with closing(connect(root / project / 'Sessions/Sessions.sqlite')) as db:
                    db.execute('BEGIN')
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    for meta in records:
                        row = db.execute("SELECT r.id,r.session_id,r.state,r.busy,r.worker,json_extract(r.config,'$.goalExecution.requestId') AS goal_execution FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND r.session_id=? AND s.project_id=?",
                            (meta['runId'], meta['sessionId'], project)).fetchone()
                        if row is None or not executing(db, row, tables): continue
                        worker = json.loads(row['worker'] or '{}')
                        if (type(worker.get('pid')) is not int or worker['pid'] <= 0 or worker.get('release') != meta['release']
                                or not isinstance(worker.get('birth'), str)): continue
                        candidates.append((project, meta['runId'], worker))
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error): continue
        current = await read_units([UNIT.format(run) for _, run, _ in candidates])
        active = set()
        for project, run, worker in candidates:
            try:
                unit = current.get(UNIT.format(run), {})
                pid = worker['pid']
                if (unit.get('ActiveState') in ('active', 'activating', 'deactivating', 'reloading')
                        and int(unit.get('MainPID', '0')) == pid
                        and (Path('/proc') / str(pid)).stat().st_uid == host.config['uid']
                        and birth(pid) == worker['birth']): active.add(project)
            except (OSError, ValueError, KeyError, TypeError): continue
        return {'schema': 1, 'activeProjectIds': sorted(active), 'checkedAt': now(), 'validForMs': 10000}
    except (OSError, ValueError, sqlite3.Error, asyncio.TimeoutError):
        raise ProjectFault('Project activity is temporarily unavailable.', 503) from None
