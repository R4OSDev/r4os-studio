#!/usr/bin/env python3
"""One immutable accepted Git job, never restarted automatically after uncertain effects."""
import json
import os
from pathlib import Path
import resource
import fcntl
import sys
from common import ProjectFault, document, folder, locks, now, save
from operations import Operations


def main():
    os.umask(0o077)
    config = document(Path(sys.argv[1])); identity = sys.argv[2]
    from common import project_id
    project_id(identity)
    path = folder(Path(config['projects']) / '.studio/github/Jobs' / identity) / 'job.json'
    execution = open(path.with_name('execution.lock'), 'a')
    fcntl.flock(execution, fcntl.LOCK_EX | fcntl.LOCK_NB)
    job = document(path)
    if job['id'] != identity or job['state'] != 'queued' or job['releaseRoot'] != str(Path(__file__).resolve().parents[2]):
        raise ProjectFault('Git job binding changed. Original data was preserved.', 409)
    resource.setrlimit(resource.RLIMIT_FSIZE, (268435456, 268435456))
    from host import birth
    job.update(state='running', phase='starting', updatedAt=now(), workerPid=os.getpid(), workerBirth=birth(os.getpid()))
    save(path, job)
    try:
        with locks(config['projects'], job['projectId'], mutate=job['kind'] not in ('status', 'check')):
            result = Operations(config, job).execute()
        job.update(state='completed', phase='complete', result=result, updatedAt=now())
    except ProjectFault as error:
        # Errors before publication have no source effect. Network/publication ambiguity is retained.
        uncertain = job.get('effectPossible', False) or (job['phase'] not in ('starting', 'validating') and error.code >= 500)
        job.update(state='unknown' if uncertain else 'failed', error=str(error), code=error.code, updatedAt=now())
    except BaseException:
        job.update(state='unknown', error='Git job could not confirm its result. Reconcile the original request.', code=503, updatedAt=now())
    save(path, job)
    execution.close()


if __name__ == '__main__': main()
