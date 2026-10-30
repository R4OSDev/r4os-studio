"""Freeze qualified retry capabilities before leases; preserve old queue bytes."""
from store import ProjectFault

FIELDS=('goalRetryProtocol','claudeRetryProtocol')


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
    from profile import CODEX_VERSION,CODEX_SHA256
    if engine.get('version')!=CODEX_VERSION or engine.get('sha256')!=CODEX_SHA256:return {}
    if not snapshot.get('apiProvider'):
        from image_provider import selection
        if not selection(engine.get('profile')):return {}
    return {'goalRetryProtocol':1}


def freeze(snapshot,original=None):
    """original is trusted stored configuration, never a client capability map."""
    available=offered(snapshot)
    for field in FIELDS:
        if original is not None:
            if field not in original:
                snapshot.pop(field,None);continue
            if type(original[field]) is not int or original[field]!=1 or available.get(field)!=1:
                raise ProjectFault('The saved retry protocol is unavailable. Preserve the original queue and submit explicitly after review.',409)
        if field in available:snapshot[field]=available[field]
        else:snapshot.pop(field,None)
