"""Confirmed, restartable deletion of one UUID project; never manages a VM."""
from contextlib import closing, ExitStack
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys

from store import connect, ProjectFault
from layout import folder, sync
from project_use import acquire, project_id

AGENT_RUNTIME = Path('/run/r4os-studio-agents')
DEVELOPMENT_RUNTIME = Path('/run/r4os-studio-development')

def document(path):
    path = Path(path)
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 131072:
        raise ProjectFault('Invalid project worker record. Existing data was preserved.', 503)
    return json.loads(path.read_text())


def rows(path, table, columns='*'):
    if not path.exists() and not path.is_symlink(): return []
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ProjectFault('Invalid project state. Existing data was preserved.', 503)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ProjectFault('Project state needs maintenance before deletion.', 503)
        return [dict(r) for r in db.execute('SELECT ' + columns + ' FROM ' + table)]


def worker_check(runs, jobs, action='deleting'):
    units = ['r4os-studio-agent@' + value + '.service' for value in runs]
    units += [('r4os-studio-development@' if kind in ('build','package') else 'r4os-studio-development-vm@') + value + '.service' for value, kind in jobs.items()]
    for start in range(0, len(units), 128):
        result = subprocess.run(['/usr/bin/systemctl', 'show', *units[start:start+128], '--property=ActiveState', '--value'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
        states = result.stdout.decode().split()
        if result.returncode or len(states) != len(units[start:start+128]):
            raise ProjectFault(f'Worker status could not be verified. Restore host support before {action}.', 503)
        if any(state not in ('inactive', 'failed') for state in states):
            raise ProjectFault(f'Wait for this project\'s runs and development jobs to finish before {action}.', 409)


def collect(projects, ident, hosts):
    from remote_binding import assert_change_safe
    assert_change_safe(projects, ident)
    if hosts.get('unsafe'):
        raise ProjectFault('Wait for the updated project hosts to become ready before deleting. Existing data was preserved.', 503)
    from project_maintenance import pending_update, pending_git
    if pending_git(projects, ident): raise ProjectFault('Reconcile the original Git pull before deleting its recovery data.', 409)
    if pending_update(projects,ident):
        raise ProjectFault('Resolve this project\'s owned native update before deleting its package/recovery evidence.',409)
    project = projects / ident
    if project.exists() or project.is_symlink(): folder(project)
    sessions = rows(project / 'Sessions/Sessions.sqlite', 'sessions', 'id')
    runs = rows(project / 'Sessions/Sessions.sqlite', 'runs', 'id,busy')
    jobs = rows(project / 'Development/Development.sqlite', 'jobs', "id,kind,state,busy,CASE WHEN kind='execution' AND state='unknown' THEN payload ELSE '{}' END AS payload")
    if any(r['busy'] for r in runs + jobs):
        raise ProjectFault('Stop this project\'s runs and development jobs before deleting it.', 409)
    if sessions and not hosts.get('agents'):
        raise ProjectFault('Wait for the updated agent host to become ready before deleting a project with sessions.', 503)
    if (project / 'Development/Development.sqlite').exists() and not hosts.get('development'):
        raise ProjectFault('Wait for the updated development host to become ready before deleting this project.', 503)
    run_ids = {project_id(r['id']) for r in runs}
    job_ids = {project_id(j['id']): j['kind'] for j in jobs}
    for job in jobs:
        value = json.loads(job['payload'])
        if job['kind'] == 'execution' and value.get('target') and not (value.get('guestState') or {}).get('closeConfirmed') and job['state'] == 'unknown':
            raise ProjectFault('Reconcile this project\'s unconfirmed guest execution before deleting it.', 409)
    # Include orphaned, but positively attributed, host records as well.
    for kind, root in [('agents', projects / '.studio/agents'), ('development', projects / '.studio/development')]:
        for path in root.glob('*/worker.json'):
            if path.parent.name in run_ids or path.parent.name in job_ids:
                value = document(path)
                if value.get('projectId') != ident: raise ProjectFault('A worker record belongs to another project.', 409)
            else:
                try: value = document(path)
                except Exception: continue
            if value.get('projectId') != ident: continue
            key = project_id(value['runId' if kind == 'agents' else 'jobId'])
            if key != path.parent.name: raise ProjectFault('Invalid worker identity.', 503)
            if kind == 'agents': run_ids.add(key)
            else: job_ids[key] = value.get('kind', 'build')
    worker_check(sorted(run_ids), job_ids)
    development = projects / '.studio/development'
    leases = []
    for path in (development / 'leases').glob('*.json'):
        try: value = document(path)
        except Exception: continue  # Never infer ownership of an unrelated damaged record.
        scope = value.get('scope') or {}
        if scope.get('projectId') != ident and scope.get('jobId') not in job_ids: continue
        key = project_id(path.stem)
        if not value.get('closedAt'):
            raise ProjectFault('A project VM reservation is not closed. Reconcile its job before deleting.', 409)
        leases.append(key)
    for path in (development / 'Forwards').glob('*.json'):
        try: value = document(path)
        except Exception:
            if path.stem in leases: raise
            continue
        scope = value.get('scope') or {}
        if path.stem in leases or scope.get('projectId') == ident or scope.get('jobId') in job_ids:
            if value.get('state') != 'closed': raise ProjectFault('A project VM connection still needs cleanup before deletion.', 409)
            if path.stem not in leases: leases.append(project_id(path.stem))
    for path in (development / 'Unconfirmed').glob('*.json'):
        try: value = document(path)
        except Exception: continue
        if value.get('projectId') == ident or value.get('jobId') in job_ids:
            raise ProjectFault('Reconcile this project\'s unconfirmed guest effects before deleting it.', 409)
    return {'projectId': ident, 'runs': sorted(run_ids), 'jobs': sorted(job_ids), 'leases': sorted(leases)}


def remove(path):
    if not path.exists() and not path.is_symlink(): return
    # rmtree uses dir-fd operations and unlinks contained symlinks without
    # following them. The top-level project/host directory itself must be real.
    if path.is_symlink() or path.parent.resolve(strict=True) != path.parent:
        raise ProjectFault('Invalid deletion target. No linked directory was followed.', 503)
    if path.is_dir():
        if not shutil.rmtree.avoids_symlink_attacks: raise ProjectFault('Safe directory deletion is unavailable.', 503)
        shutil.rmtree(path)
    elif path.is_file(): path.unlink()
    else: raise ProjectFault('Invalid project deletion target.', 503)
    sync(path.parent)


def finish(db, projects, journal):
    ident = project_id(journal['projectId'])
    for key in ('runs', 'jobs', 'leases'):
        for value in journal[key]: project_id(value)
    for group, key in [('agents', 'runs'), ('development', 'jobs')]:
        for value in journal[key]:
            target = projects / '.studio' / group / value
            if (target / 'worker.json').exists() and document(target / 'worker.json').get('projectId') != ident:
                raise ProjectFault('A host record now belongs to another project. It was preserved.', 409)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent-sessions'))
    from stats_lifecycle import preserve_pending
    preserve_pending(projects, projects / ident / 'Sessions/Sessions.sqlite')
    remove(projects / ident)
    for run in journal['runs']:
        remove(projects / '.studio/agents' / run)
        remove(AGENT_RUNTIME / run)
    for job in journal['jobs']:
        remove(projects / '.studio/development' / job)
        remove(DEVELOPMENT_RUNTIME / 'Jobs' / job)
        remove(projects / '.studio/development/Unconfirmed/Resolved' / (job + '.json'))
    for lease in journal['leases']:
        remove(projects / '.studio/development/leases' / (lease + '.json'))
        remove(projects / '.studio/development/Forwards' / (lease + '.json'))
        remove(DEVELOPMENT_RUNTIME / 'auth' / lease)
    for path in (projects / '.studio/layouts').glob(ident + '*.json'):
        if path.name == ident + '.json' or path.name.startswith(ident + '.previous.'): remove(path)
    for path in (projects / '.studio/staging').glob(ident + '*'):
        if path.name == ident or path.name.startswith(ident + '.interrupted.'): remove(path)
    remove(projects / '.studio' / ('workspace-' + ident + '.lock'))
    sync(projects)
    with db:
        # Only opaque original create-request fingerprints remain, so a late
        # browser retry cannot silently recreate a deleted project.
        db.execute('PRAGMA secure_delete=ON')
        db.execute('INSERT OR IGNORE INTO retired_project_requests SELECT request_key,request_hash FROM requests WHERE project_id=?', (ident,))
        db.execute('DELETE FROM requests WHERE project_id=?', (ident,))
        db.execute('DELETE FROM projects WHERE id=?', (ident,))
        db.execute('DELETE FROM project_deletions WHERE project_id=?', (ident,))
    sync(projects)
    return {'id': ident, 'deleted': True}


def delete(projects, ident, data, hosts=None):
    projects = folder(Path(projects).absolute()); project_id(ident)
    if not isinstance(data, dict) or set(data) != {'revision', 'confirm'} or type(data['revision']) is not int or data['revision'] < 1 or data['confirm'] is not True:
        raise ProjectFault('Confirm deletion of the selected project.', 400)
    with ExitStack() as stack:
        lock_path = projects / '.studio/create.lock'
        lock_path.parent.mkdir(exist_ok=True, mode=0o700)
        folder(lock_path.parent)
        if lock_path.is_symlink(): raise ProjectFault('Invalid project creation lock.', 503)
        creation = stack.enter_context(lock_path.open('a'))
        try: fcntl.flock(creation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('Project creation is in progress. Retry deletion shortly.', 409) from None
        use = stack.enter_context(acquire(projects, ident, exclusive=True))
        workspace = projects / '.studio' / ('workspace-' + ident + '.lock')
        fd = os.open(workspace, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        lease = stack.enter_context(os.fdopen(fd, 'a'))
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('The project workspace is in use. Stop its run or build first.', 409) from None
        db = stack.enter_context(closing(connect(projects)))
        journal = db.execute('SELECT * FROM project_deletions WHERE project_id=?', (ident,)).fetchone()
        if journal:
            if journal['revision'] != data['revision']: raise ProjectFault('Reload the project before retrying deletion.', 409)
            result = finish(db, projects, json.loads(journal['payload']))
        else:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM projects WHERE id=?', (ident,)).fetchone()
            if row is None:
                db.rollback()
                if (projects / ident).exists() or (projects / ident).is_symlink(): raise ProjectFault('An unregistered directory was preserved.', 409)
                result = {'id': ident, 'deleted': True}
            else:
                if row['state'] != 'ready' or row['revision'] != data['revision']:
                    raise ProjectFault('Project settings changed. Reload before deleting.', 409)
                plan = collect(projects, ident, hosts or {})
                db.execute('INSERT INTO project_deletions VALUES (?,?,?)', (ident, data['revision'], json.dumps(plan)))
                db.execute("UPDATE projects SET state='failed' WHERE id=?", (ident,))
                db.commit()  # Irrevocable confirmed intent; resume, never archive.
                result = finish(db, projects, plan)
        workspace.unlink(missing_ok=True)
        use.close()
        (projects / '.studio/project-use' / (ident + '.lock')).unlink(missing_ok=True)
        return result


def recover(projects):
    projects = Path(projects).absolute()
    with closing(connect(projects)) as db: pending = db.execute('SELECT project_id,revision FROM project_deletions').fetchall()
    results = []
    for row in pending:
        try: delete(projects, row['project_id'], {'revision': row['revision'], 'confirm': True}); complete = True
        except Exception: complete = False
        results.append({'id': row['project_id'], 'deleted': complete})
    return results


def main():
    os.umask(0o077)
    data = sys.stdin.buffer.read(16385)
    if len(data) > 16384: raise ProjectFault('Invalid deletion request.', 400)
    request = json.loads(data)
    if request == {'operation': 'recover'}: result = recover(sys.argv[1])
    elif request.get('operation') == 'delete' and set(request) == {'operation', 'id', 'input', 'hosts'}:
        result = delete(sys.argv[1], request['id'], request['input'], request['hosts'])
    else: raise ProjectFault('Invalid deletion operation.', 400)
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Project deletion could not finish. Retry deletion; its confirmed progress was preserved.', 'code': 503})); sys.exit(1)
