"""Pinned native Claude SDK runtime, distinct from Codex and API transports."""
import hashlib
import json
from pathlib import Path

from api_provider_store import private
from session_store import identity
from store import ProjectFault


def profile():
    return json.loads((Path(__file__).resolve().parents[2]/'shared/claude-subscription-profile.json').read_text())


def verify(path,expected=None):
    expected=expected or profile();path=Path(path).absolute()
    try:
        private(path,directory=True)
        manifest=path/'profile.json';private(manifest)
        if json.loads(manifest.read_text())!=expected:raise ValueError()
        for kind in ('sdk','native'):
            root=path/kind;private(root,directory=True)
            if {p.name for p in root.iterdir()}!=set(expected[kind]['files']):raise ValueError()
            for name,pin in expected[kind]['files'].items():
                item=root/name;mode=0o700 if pin.get('executable') else 0o600
                info=item.lstat()
                if item.resolve(strict=True)!=item or info.st_nlink!=1 or info.st_size!=pin['bytes'] or info.st_mode&0o777!=mode:
                    raise ValueError()
                # private() enforces owner/type/link invariants for data files;
                # executable bytes intentionally use the separate0700 mode.
                if mode==0o600:private(item)
                elif info.st_uid!=path.stat().st_uid or info.st_gid!=path.stat().st_gid or not item.is_file():raise ValueError()
                with item.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=pin['sha256']:raise ValueError()
        return {'id':expected['id'],'sdk':str(path/'sdk/sdk.mjs'),'native':str(path/'native/claude'),
            'version':expected['native']['version'],'sdkVersion':expected['sdk']['version'],
            'sha256':expected['native']['files']['claude']['sha256'],'sdkArchiveSha256':expected['sdk']['archiveSha256'],
            'qualified':dict(expected['qualified'])}
    except (OSError,ValueError,KeyError,TypeError,ProjectFault):
        raise ProjectFault('The pinned Claude runtime is missing or changed. Preserve existing data and explicitly install its verified profile.',503) from None


def installed(providers):
    expected=profile();return verify(Path(providers).absolute()/'ClaudeRuntime'/expected['id'],expected)


def binding(provider,sid,native_session=None):
    expected=profile()
    if (provider.get('type')!='claude-subscription' or type(provider.get('profileRevision')) is not int or provider.get('profileRevision')!=1
            or provider.get('runtimeProfileId')!=expected['id']):
        raise ProjectFault('The original Claude provider runtime binding is unavailable.',409)
    return {'kind':'claude-code','profile':expected['adapterProfile'],'profileRevision':1,
        'providerId':identity(provider['id']),'studioSessionId':identity(sid),
        'nativeSessionId':identity(native_session) if native_session is not None else None,
        'runtimeProfileId':expected['id'],'version':expected['native']['version'],
        'sha256':expected['native']['files']['claude']['sha256'],'sdkVersion':expected['sdk']['version'],
        'sdkArchiveSha256':expected['sdk']['archiveSha256']}
