"""Collect only files registered before execution, within this deployment."""
import hashlib
from contracts import DevelopmentFault
from evidence import publish
from sftp import download


async def collect(store, job, deployment, ssh, work):
    values = []
    parts = deployment['guestDirectory'].replace('\\', '/').split('/')
    directory = '/C/' + '/'.join(part for part in parts[1:] if part)
    for index, spec in enumerate(job['settings'].get('outputFiles', [])):
        local = work / ('result-' + str(index))
        try:
            exists = await download(ssh, directory + '/' + spec['name'], local, maximum=65536, allow_missing=True)
            if not exists: continue
            data = local.read_bytes()
            receipt = publish(store, job, 'file', data, name=spec['name'], source='registered-deployment-file',
                containsExpectedText=spec['contains'] is None or spec['contains'] in data.decode('utf-8', errors='replace'))
            values.append(receipt); local.unlink()
        except DevelopmentFault as error:
            values.append({'name': spec['name'], 'error': str(error)})
    return values
