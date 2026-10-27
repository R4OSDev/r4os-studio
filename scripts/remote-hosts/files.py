"""Original transfer jobs; native paths and honest create-only capabilities."""
import asyncio
import base64
import hashlib
from catalog import CatalogFault, fields, identity, integer
from sftp_client import RemoteSftp, path
import file_access as local
import job_store as jobs


def arguments(value):
    if not isinstance(value, dict): raise CatalogFault('Invalid remote file arguments.', 400)
    op = value.get('action'); required = ['requestId', 'action', 'path']; optional = []
    if op == 'list': pass
    elif op == 'read': optional = ['maxBytes']
    elif op == 'upload':
        required += ['sha256'] + (['sourcePath'] if 'sourcePath' in value else ['artifactId', 'artifactPath'])
    elif op == 'download': required += ['localPath', 'expectedSha256', 'remoteSha256']
    else: raise CatalogFault('Supported SFTP actions are list, read, upload and download. No overwrite, rename, delete or FTP fallback is available.', 400)
    fields(value, required, optional); identity(value['requestId']); path(value['path'])
    if op == 'read': integer(value.get('maxBytes', 16384), 16384)
    if op == 'upload':
        local.digest(value['sha256'])
        if 'sourcePath' in value: local.relative(value['sourcePath'])
        else: identity(value['artifactId']); local.relative(value['artifactPath'])
    if op == 'download': local.relative(value['localPath']); local.digest(value['remoteSha256'])
    return dict(value)


def prepare(actor, job_id, content):
    if content['action'] == 'upload': return {'snapshot': local.snapshot(actor, job_id, content)}
    if content['action'] == 'download': return {'workspaceIdentity': local.destination(actor, content)}
    return {}


async def perform(client, projects, project_id, job_id, payload, abort):
    content = payload['files']; action = content['action']
    def guard():
        if abort.is_set(): raise CatalogFault('The original remote file job was stopped. It was not repeated.', 409)
    def effect_guard():
        from actor import still_running
        guard()
        if not still_running(projects, payload['actor']): raise CatalogFault('The original run ended before the file effect.', 409)
    factory = getattr(client, 'sftp', RemoteSftp)
    async def effect():
        async with factory(client, guard) as remote:
            if action == 'list': return await remote.listing(content['path'])
            if action == 'upload':
                raw = local.snapshot_bytes(projects, project_id, payload['snapshot'])
                def before_write():
                    effect_guard(); jobs.update(projects, project_id, job_id, 'running', 'dispatch_possible')
                def progress(value): jobs.update(projects, project_id, job_id, 'running', 'dispatch_possible', {'transferProgress': value})
                return await remote.put(content['path'], raw, before_write, progress)
            raw = await remote.get(content['path'], content.get('maxBytes', 16384) if action == 'read' else local.MAX_FILE)
            guard()
            if action == 'read':
                try: text = raw.decode('utf8'); encoding = 'utf8'
                except UnicodeError: text = base64.b64encode(raw).decode('ascii'); encoding = 'base64'
                return {'path': content['path'], 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'content': text, 'encoding': encoding, 'fullReadVerified': True}
            def before_publish():
                effect_guard(); jobs.update(projects, project_id, job_id, 'running', 'local_publish_possible')
            return {**local.publish(projects, project_id, content, raw, payload['workspaceIdentity'], before_publish), 'path': content['path'], 'fullReadVerified': True}
    work = asyncio.create_task(effect()); stopping = asyncio.create_task(abort.wait())
    try:
        done, _ = await asyncio.wait((work, stopping), timeout=120, return_when=asyncio.FIRST_COMPLETED)
        if work in done: return work.result()
        raise CatalogFault('The original SFTP job stopped or exceeded its120-second deadline. Inspect its original receipt; do not repeat a possible effect.', 409)
    finally:
        for task in (work, stopping):
            if not task.done(): task.cancel()
        await asyncio.gather(work, stopping, return_exceptions=True)
