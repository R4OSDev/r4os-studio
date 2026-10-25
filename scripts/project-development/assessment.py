"""Visual judgments are attributed separately from automatic assertions."""
from contracts import DevelopmentFault, identity
from evidence import read
from checks import evaluate
from jobs import now


def record(store, job_id, value, actor='user', actor_id=None):
    if not isinstance(value, dict) or set(value) != {'requestId', 'evidenceId', 'settingsRevision', 'state', 'notes'}:
        raise DevelopmentFault('Unexpected visual assessment fields.', 400)
    identity(value['requestId'])
    from actions import admit, finish
    job = store.get(job_id); image = read(store, job_id, value['evidenceId'])['metadata']
    if image['kind'] != 'screenshot' or value['settingsRevision'] != job['settingsRevision'] or not job['settings'].get('visualCriteria'):
        raise DevelopmentFault('This image has no matching configured visual criteria.')
    if value['state'] not in ('passed', 'failed', 'inconclusive') or not isinstance(value['notes'], str) or not 0 < len(value['notes'].encode()) <= 1024 or '\x00' in value['notes']:
        raise DevelopmentFault('Enter a bounded visual assessment.', 400)
    if job.get('checkCompletion'): raise DevelopmentFault('This check result is already completing or closed.')
    receipt = admit(store, job_id, {'operation': 'assess', **value, 'actor': actor, 'actorId': actor_id})
    if receipt is not None: return store.get(job_id)
    assessment = {**value, 'actor': actor, 'actorId': actor_id, 'imageSha256': image['sha256'], 'createdAt': now()}
    output = store.evidence(job_id) / 'output.log'
    check = evaluate(job['settings'], job.get('guestState') or {}, output.read_bytes() if output.exists() else b'',
        job.get('outputFiles', []), assessment)
    result = store.annotate(job_id, visualAssessment=assessment, check=check)
    finish(store, value['requestId'], {'assessment': assessment})
    return result
