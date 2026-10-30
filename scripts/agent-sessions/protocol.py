"""Agent compatibility ceiling. Old releases are supported rollback targets."""
import json
from pathlib import Path

EXPECTED = {'agentHostProtocol': 1, 'agentWorkerProtocol': 1, 'agentDataSchema': 1}
PROFILES = ('studio-tools-v1', 'studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4', 'studio-skill-tools-v1', 'studio-skill-tools-v2', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-skill-tools-v3','studio-tools-v11','studio-skill-tools-v4','studio-tools-v12','studio-tools-v13','studio-tools-v14','studio-tools-v15','studio-skill-tools-v5')


def supported_profiles(root):
    root = Path(root); value = json.loads((root / 'shared/update-host.json').read_text())
    profiles = value.get('agentToolProfiles')
    if profiles is None:
        # The published 0.3.24 release qualified v2 before this declaration was
        # added. Earlier releases remain v1-only rollback targets.
        version = json.loads((root / 'shared/version.json').read_text())['version']
        return PROFILES[:2] if version == '0.3.24' else PROFILES[:1]
    if not isinstance(profiles, list) or not profiles or any(p not in PROFILES for p in profiles): raise ValueError('This release requires a newer agent host.')
    return tuple(profiles)


def release_protocol(root):
    if not (Path(root) / 'scripts/agent-sessions/worker.py').is_file(): raise ValueError('This release has no compatible agent worker.')
    value = json.loads((Path(root) / 'shared/update-host.json').read_text())
    declared = {k: value[k] for k in EXPECTED if k in value}
    if declared and declared != EXPECTED: raise ValueError('This release requires agent host maintenance.')
    supported_profiles(root)
    return EXPECTED


def validate_release(value, base=Path('/opt/r4os-studio/releases')):
    release = Path(value['releaseRoot']).resolve(strict=True)
    if not release.is_relative_to(base): raise ValueError('Invalid worker release.')
    release_protocol(release)
    info = json.loads((release / 'release.json').read_text())
    if info['id'] != value['release'] or info['version'] != value['version']: raise ValueError('The original worker release identity changed.')
