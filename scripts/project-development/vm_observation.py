"""A bounded QMP observation job. It never launches an application or a VM."""
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from observation import capture
from vm_worker import broker_call, guard
from jobs import now


def require_context(config, project, vm):
    context = config.get('vmObservation') or {}
    expected = {'version': 1, 'available': True, 'projectRevision': project['revision'],
        'vmId': project['vmId'], 'vmRevision': vm['revision'],
        'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
    if any(context.get(key) != value for key, value in expected.items()):
        raise DevelopmentFault('VM diagnosis requires the same project assignment and VM image frozen in this accepted input. Use a new input after reviewing changed settings.', 409,
                               reason_code='vm_observation_context_changed')


async def run(store, job):
    from queue_lease import reserve
    from actions import admit, finish
    from evidence import read
    vm = job['binding']
    scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
        'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
    async with reserve(store, job, scope) as lease:
        guard(store, job, lease)
        result = await broker_call({'operation': 'bind_observation_target', 'projectId': store.id,
            'jobId': job['id'], 'leaseId': lease.id, 'token': lease.token})
        scope['bootId'] = result['bootId']
        from layout import save
        save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
        job = store.get(job['id'])
        guard(store, job, lease)
        owner = {'sessionId': job['sessionId'], 'agentRunId': job['agentRunId']}
        message = {'operation': 'capture', 'requestId': job['requestId'], 'owner': owner, 'scope': 'vm'}
        previous = admit(store, job['id'], message)
        if previous is not None:
            if previous.get('error'): raise DevelopmentFault(previous['error'], previous.get('code', 409))
            data = read(store, job['id'], previous['evidenceId'])
        else:
            store.update(job['id'], phase='capturing', captureState='pending')
            try:
                data = await capture(store, job, lease, observer=owner,
                    origin={'requestId': job['requestId'], 'operation': 'capture'}, vm_diagnostic=True,
                    validate=lambda: guard(store, job, lease))
                finish(store, job['requestId'], {'evidenceId': data['metadata']['id']})
            except BaseException as error:
                # A possibly dispatched QMP read is never repeated to recover an image.
                raise UnconfirmedGuestEffect('The original VM observation was not confirmed. Inspect its saved job and image receipts; no capture was repeated.') from error
        guard(store, job, lease)
        return store.update(job['id'], 'completed', phase='observed', captureState='confirmed',
            evidenceId=data['metadata']['id'], observationMode='vm-diagnostic',
            readiness={'state': 'observed', 'checkedAt': now(), 'reason': 'VM screen only; no app readiness, input reference or test proof.'})
