"""Explicit, project-bound cache maintenance; never runs a compiler or a VM."""
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import sys

from store import ProjectFault
from layout import folder, project_directory, save, sync
from project_use import acquire, project_id
from project_maintenance import project, busy, require_idle
from delete import document, rows, worker_check


def cache_path(directory):
    development = directory / 'Development'
    if development.exists() or development.is_symlink(): folder(development)
    path = development / 'Cache'
    if path.exists() or path.is_symlink(): folder(path)
    return path


def worker_admission(projects, identity, hosts):
    if not isinstance(hosts, dict) or hosts.get('unsafe'):
        raise ProjectFault('Wait for the updated project hosts before clearing the build cache.', 503)
    root = project_directory(projects, identity)
    runs = rows(root / 'Sessions/Sessions.sqlite', 'runs', 'id,busy')
    jobs = rows(root / 'Development/Development.sqlite', 'jobs', 'id,kind,busy')
    if any(value['busy'] for value in runs + jobs):
        raise ProjectFault('Wait for active agent runs and development jobs to finish.', 409)
    if (runs and not hosts.get('agents')) or ((root / 'Development/Development.sqlite').exists() and not hosts.get('development')):
        raise ProjectFault('Project worker status is unavailable. Restore its host before clearing the build cache.', 503)
    run_ids = {project_id(value['id']) for value in runs}
    job_ids = {project_id(value['id']): value['kind'] for value in jobs}
    for kind in ('agents', 'development'):
        for path in (projects / '.studio' / kind).glob('*/worker.json'):
            known = path.parent.name in (run_ids if kind == 'agents' else job_ids)
            try: value = document(path)
            except Exception:
                if known: raise
                continue
            if value.get('projectId') != identity:
                if known: raise ProjectFault('A worker record belongs to another project.', 503)
                continue
            key = project_id(value['runId' if kind == 'agents' else 'jobId'])
            if key != path.parent.name: raise ProjectFault('Invalid project worker identity.', 503)
            if kind == 'agents': run_ids.add(key)
            else: job_ids[key] = value.get('kind', 'build')
    worker_check(sorted(run_ids), job_ids, 'clearing the build cache')


def hold_cache_locks(path, stack):
    # Also detect an older cache user whose service/DB has already stopped.
    # Project-use remains held outside the tree, so new admission cannot race.
    for child in path.iterdir():
        if child.is_symlink() or not child.is_dir(): continue
        folder(child)
        lock = child / 'lock'
        try: fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError: continue
        except OSError: raise ProjectFault('A compiler cache lock cannot be verified.', 409) from None
        stream = stack.enter_context(os.fdopen(fd, 'r+b'))
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProjectFault('Invalid compiler cache lock.', 409)
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('A build is still using this project cache. Wait for it to finish.', 409) from None


def identity_of(path):
    info = path.lstat()
    return [info.st_dev, info.st_ino, info.st_ctime_ns]


def result_of(receipt):
    superseded = receipt.get('superseded', False)
    return {'requestId': receipt['requestId'], 'cleared': not superseded,
            'changed': receipt['cacheIdentity'] is not None and not superseded, 'superseded': superseded}


def read_receipt(path, identity, request_id):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 32768:
            raise ProjectFault('Invalid build cache maintenance receipt.', 503)
        data = stream.read(32769)
    value = json.loads(data)
    if (value.get('schema') != 1 or value.get('projectId') != identity or value.get('requestId') != request_id
            or value.get('phase') not in ('prepared', 'detached', 'complete')
            or (value.get('cacheIdentity') is not None and (not isinstance(value['cacheIdentity'], list)
                or len(value['cacheIdentity']) != 3 or any(type(n) is not int for n in value['cacheIdentity'])))):
        raise ProjectFault('Invalid build cache maintenance identity.', 503)
    return value


def receipt_directories(directory):
    root = directory / '.studio/cache-clear'
    for path in (directory / '.studio', root, root / 'Pending', root / 'Completed'):
        if path.exists() or path.is_symlink(): folder(path)
    return root


def pending_receipt(receipts, identity):
    paths = list((receipts / 'Pending').glob('*.json'))
    if len(paths) > 1:
        raise ProjectFault('Multiple unfinished cache cleanups need host maintenance.', 503)
    if not paths: return None
    return read_receipt(paths[0], identity, project_id(paths[0].stem))


def complete_receipt(receipts, journal, receipt):
    receipt['phase'] = 'complete'; save(journal, receipt)
    completed = receipts / 'Completed'
    completed.mkdir(mode=0o700, exist_ok=True); folder(completed); sync(receipts)
    os.replace(journal, completed / journal.name)
    sync(journal.parent); sync(completed)
    return result_of(receipt)


def clear(projects, identity, request_id, hosts):
    project_id(request_id)
    with ExitStack() as stack:
        stack.enter_context(acquire(projects, identity, exclusive=True))
        project(projects, identity)
        directory = project_directory(projects, identity)
        receipts = receipt_directories(directory)
        completed = receipts / 'Completed' / (request_id + '.json')
        if completed.exists() or completed.is_symlink():
            receipt = read_receipt(completed, identity, request_id)
            if receipt['phase'] != 'complete': raise ProjectFault('Invalid completed cache receipt.', 503)
            return result_of(receipt)
        receipt = pending_receipt(receipts, identity)
        if receipt and receipt['requestId'] != request_id:
            raise ProjectFault('An earlier cache cleanup needs retry. Reload its status before clearing again.', 409)
        journal = receipts / 'Pending' / (request_id + '.json')
        if receipt and receipt['phase'] == 'complete':
            return complete_receipt(receipts, journal, receipt)
        require_idle(projects, identity)
        worker_admission(projects, identity, hosts)
        cache = cache_path(directory)
        detached = cache.with_name('.cache-clear-' + request_id)
        if receipt is None:
            if detached.exists() or detached.is_symlink():
                raise ProjectFault('Unattributed cache maintenance data was preserved.', 409)
            journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(journal.parent)
            sync(receipts); sync(receipts.parent); sync(directory)
            receipt = {'schema': 1, 'projectId': identity, 'requestId': request_id,
                       'phase': 'prepared', 'cacheIdentity': identity_of(cache) if cache.exists() else None}
            save(journal, receipt)
        original = receipt['cacheIdentity']
        locks_held = False
        if original is not None:
            if detached.exists() or detached.is_symlink():
                folder(detached)
                if identity_of(detached)[:2] != original[:2]:
                    raise ProjectFault('Detached cache identity changed. Existing data was preserved.', 409)
            elif receipt['phase'] == 'prepared':
                if not cache.exists() or identity_of(cache) != original:
                    # No old detached tree remains. An explicit new request is
                    # required to affect a cache recreated/changed meanwhile.
                    receipt['superseded'] = True
                    return complete_receipt(receipts, journal, receipt)
                hold_cache_locks(cache, stack)
                locks_held = True
                os.rename(cache, detached); sync(cache.parent)
            if receipt['phase'] == 'prepared':
                receipt['phase'] = 'detached'; save(journal, receipt)
            if detached.exists():
                if not locks_held: hold_cache_locks(detached, stack)
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise ProjectFault('Safe cache deletion is unavailable on this host.', 503)
                # Dir-fd based rmtree unlinks internal links, including zig/p,
                # without ever walking their targets.
                shutil.rmtree(detached); sync(cache.parent)
        return complete_receipt(receipts, journal, receipt)


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192: raise ProjectFault('Cache maintenance request is too large.', 400)
    request = json.loads(raw); operation = request.get('operation')
    projects = folder(Path(sys.argv[1]).absolute()); identity = project_id(request.get('id'))
    if operation == 'status' and set(request) == {'operation', 'id'}:
        with acquire(projects, identity):
            project(projects, identity)
            directory = project_directory(projects, identity)
            receipt = pending_receipt(receipt_directories(directory), identity)
            result = {'available': not busy(projects, identity), 'pendingRequestId': receipt['requestId'] if receipt else None}
    elif operation == 'clear' and set(request) == {'operation', 'id', 'requestId', 'hosts'}:
        result = clear(projects, identity, request['requestId'], request['hosts'])
    else: raise ProjectFault('Invalid cache maintenance request.', 400)
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Build cache cleanup is incomplete. Retry the same request to finish.', 'code': 503})); sys.exit(1)
