"""Freeze qualified retry capabilities before leases; preserve old queue bytes."""
from store import ProjectFault

FIELDS=('goalRetryProtocol','claudeRetryProtocol','streamRetryProtocol')


def offered(snapshot):
    engine=snapshot['engine']
    if engine.get('kind')=='claude-code':
        from claude_runtime import profile,text_profile
        pin=profile();runtime=engine.get('claude') or {}
        if (snapshot.get('claudeProvider') and snapshot.get('claudeSessionProfileId')==text_profile()['id']
            and runtime.get('runtimeProfileId')==pin['id'] and runtime.get('sha256')==pin['native']['files']['claude']['sha256']
            and runtime.get('sdkVersion')==pin['sdk']['version'] and runtime.get('sdkArchiveSha256')==pin['sdk']['archiveSha256']):
            return {'claudeRetryProtocol':1}
        return {}
    from codex_runtime import native
    if not native(engine):return {}
    if not snapshot.get('apiProvider'):
        from image_provider import PROVIDER
        if snapshot.get('nativeModelProvider', PROVIDER) != PROVIDER:return {}
    return {'goalRetryProtocol':1,'streamRetryProtocol':2}


def freeze(snapshot,original=None):
    """original is trusted stored configuration, never a client capability map."""
    available=offered(snapshot)
    for field in FIELDS:
        if original is not None:
            if field not in original:
                snapshot.pop(field,None);continue
            versions=(1,2) if field=='streamRetryProtocol' else (1,)
            if (type(original[field]) is not int or original[field] not in versions
                or available.get(field) not in versions or original[field]>available[field]):
                raise ProjectFault('The saved retry protocol is unavailable. Preserve the original queue and submit explicitly after review.',409)
            snapshot[field]=original[field]
            continue
        if field in available:snapshot[field]=available[field]
        else:snapshot.pop(field,None)
