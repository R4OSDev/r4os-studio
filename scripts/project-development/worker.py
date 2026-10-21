#!/usr/bin/env python3
"""One bounded development job in an independent unprivileged service."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal
import sys

from contracts import ACTIVE, DevelopmentFault, LIMITS, protocol
from jobs import Jobs
from snapshot import capture
from builder import Builder


async def main():
    os.umask(0o077)
    meta = json.loads(Path(sys.argv[1]).read_text()); protocol(Path(__file__).resolve().parents[2])
    store = Jobs(meta['projects'], meta['r4os'], meta['projectId']); job = store.get(meta['jobId'])
    if len(sys.argv) > 2:
        if job['state'] in ACTIVE:
            stopped = job['kind'] == 'build' and job['state'] == 'stopping'
            store.update(job['id'], 'interrupted' if stopped else 'unknown', phase='stopped' if stopped else 'recovery',
                error='Build stopped.' if stopped else 'The worker ended without a confirmed result. Effects were not replayed.')
        store.close(); return
    builder = Builder(store, job); interrupted = False
    async def stop():
        nonlocal interrupted
        interrupted = True; store.update(job['id'], 'stopping', phase='stopping'); await builder.stop()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, lambda: asyncio.create_task(stop()))
    try:
        if job['state'] not in ('queued', 'starting'): return
        if job['kind'] != 'build': raise DevelopmentFault('This worker release does not support this development job kind.')
        if job['projectRevision'] != store.project['revision']: raise DevelopmentFault('Project settings changed before build admission.')
        store.update(job['id'], 'running', phase='capturing')
        if job['agentRunId']:
            from agent_snapshot import delegated
            source, directory = await delegated(store, job)
        else:
            with (store.projects / '.studio' / ('workspace-' + store.id + '.lock')).open('a') as lease:
                try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: raise DevelopmentFault('This workspace is currently owned by an agent run.')
                source, directory = capture(store, job)
                store.update(job['id'], source=source)
        await asyncio.wait_for(builder.build(directory), LIMITS['buildTimeoutSeconds'])
    except asyncio.TimeoutError:
        store.update(job['id'], 'failed', phase='timeout', error='The build time limit was reached.')
    except BaseException as error:
        text = str(error) if isinstance(error, DevelopmentFault) else 'The build worker could not complete. Input and diagnostics were preserved.'
        store.update(job['id'], 'interrupted' if interrupted else 'failed', phase='stopped' if interrupted else 'failed',
            error=text, exitCode=getattr(error, 'exit_code', None))
    finally:
        await builder.stop(); store.close()


if __name__ == '__main__': asyncio.run(main())
