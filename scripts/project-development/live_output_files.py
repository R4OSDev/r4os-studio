"""Bounded observed file intervals, never process completion or an atomic snapshot."""
import asyncio
import hashlib
import json
import uuid
from contracts import DevelopmentFault
from evidence import publish, setup
from exchange import sftp_directory
from jobs import now
from sftp import download
from settings import validate

INTERVAL_SECONDS = 5
READ_BUDGET_SECONDS = 8


def owned(job, deployment, state):
    process = job.get('process') or {}
    if (job.get('kind') != 'execution' or job.get('state') != 'running'
            or state.get('state') != 'running' or state.get('closeConfirmed') or state.get('stopReason')
            or not (job.get('target') or {}).get('bootId') or not process.get('instanceId')
            or any(state.get(k) != process.get(k) for k in ('instanceId', 'generation'))
            or (deployment.get('target') or {}).get('bootId') != job['target']['bootId']
            or deployment.get('guestDirectory') != (job.get('package') or {}).get('guestDirectory')
            or deployment.get('id') != job.get('deploymentId') or deployment.get('projectId') != job.get('projectId')):
        raise DevelopmentFault('Live file checks require the original running process, boot and deployment.')


async def read_registered(job, deployment, ssh, work):
    validate(job['settings'])
    directory = sftp_directory(deployment)
    values = []
    async def read():
        for spec in job['settings']['outputFiles']:
            if asyncio.current_task().cancelling(): break
            paths = [work / ('live-' + uuid.uuid4().hex + '.bin') for _ in range(2)]
            try:
                copies = []
                for path in paths:
                    exists = await download(ssh, directory + '/' + spec['name'], path, maximum=65536, allow_missing=True)
                    copies.append(path.read_bytes() if exists else None)
                if copies[0] is None and copies[1] is None:
                    values.append({'name': spec['name'], 'state': 'missing', 'error': 'Registered output file is not present yet.'})
                elif copies[0] is None or copies[0] != copies[1]:
                    values.append({'name': spec['name'], 'state': 'unstable', 'error': 'Registered output file changed during the observed read interval.'})
                else:
                    values.append({'name': spec['name'], 'data': copies[1], 'containsExpectedText': spec['contains'] is None or spec['contains'] in copies[1].decode('utf-8', errors='replace')})
            except (DevelopmentFault, OSError):
                values.append({'name': spec['name'], 'state': 'unconfirmed', 'error': 'The registered output file could not be read within its bounds.'})
            finally:
                for path in paths: path.unlink(missing_ok=True)
    task = asyncio.create_task(read())
    done, _ = await asyncio.wait((task,), timeout=READ_BUDGET_SECONDS)
    if not done:
        task.cancel(); await asyncio.gather(task, return_exceptions=True)
        # Do not promote a partial round to a complete observation.
        return [{'name': spec['name'], 'state': 'unconfirmed', 'error': 'The live file observation exceeded its read budget.'} for spec in job['settings']['outputFiles']]
    await task
    return values


def publish_observation(store, job, values):
    setup(store)
    previous = [json.loads(r[0]) for r in store.db.execute('SELECT payload FROM evidence WHERE job_id=?', (job['id'],))]
    results = []
    for value in values:
        if 'data' not in value: results.append(value); continue
        data = value['data']; sha = hashlib.sha256(data).hexdigest()
        same = next((r for r in previous if r.get('kind') == 'file' and r.get('source') == 'live-registered-deployment-file'
            and r.get('name') == value['name'] and r.get('sha256') == sha and r.get('bytes') == len(data)
            and r.get('bootId') == job['target']['bootId'] and r.get('process') == job.get('process')
            and r.get('deploymentId') == job['deploymentId']), None)
        try:
            receipt = same or publish(store, job, 'file', data, name=value['name'], source='live-registered-deployment-file',
                deploymentId=job['deploymentId'], containsExpectedText=value['containsExpectedText'])
            results.append({**receipt, 'state': 'observed-stable', 'containsExpectedText': value['containsExpectedText']})
        except DevelopmentFault:
            results.append({'name': value['name'], 'state': 'unconfirmed', 'error': 'The live file evidence budget is unavailable. Existing receipts were preserved.'})
    return results
