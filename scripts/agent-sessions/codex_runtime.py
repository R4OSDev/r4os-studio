"""Installed Codex identities. Studio defaults select new work, never old receipts."""
import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess


def native(engine):
    return (isinstance(engine, dict) and engine.get('kind') != 'claude-code'
            and isinstance(engine.get('version'), str)
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', engine['version']) is not None
            and isinstance(engine.get('sha256'), str)
            and re.fullmatch(r'[a-f0-9]{64}', engine['sha256']) is not None)


def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=32)
def checked_digest(path, fingerprint):
    from profile import regular, digest
    file = regular(path)
    if signature(file.stat()) != fingerprint:
        raise ValueError('The Codex binary changed before its checksum could be checked.')
    checksum = digest(file)
    if signature(file.stat()) != fingerprint:
        raise ValueError('The Codex binary changed while its checksum was checked.')
    return checksum


def installed(binary, expected=None):
    from profile import regular
    binary = regular(binary)
    metadata = json.loads(regular(binary.parent / '.studio-component.json').read_text())
    version, checksum = metadata.get('version'), metadata.get('binarySha256')
    value = {'version': version, 'sha256': checksum, 'binary': str(binary), 'runtimeSelection': 1}
    fingerprint = signature(binary.stat())
    if (not native(value) or binary.name != 'codex' or binary.parent.name != version
            or metadata.get('id') != version or checked_digest(str(binary), fingerprint) != checksum
            or signature(binary.stat()) != fingerprint):
        raise ValueError('The installed Codex binary does not match its component metadata.')
    if expected is not None and (not native(expected)
            or any(expected.get(key) != value[key] for key in ('version', 'sha256'))
            or expected.get('binary', str(binary)) != str(binary)):
        raise ValueError('The original Codex installation changed. The accepted request was preserved.')
    return value


def binary(r4os, engine):
    if not native(engine):
        raise ValueError('The original Codex runtime identity is unavailable.')
    path = Path(r4os).absolute() / 'Toolchains/Codex' / engine['version'] / 'codex'
    installed(path, engine)
    return path


def selected(r4os, scope):
    root = Path(r4os).absolute()
    record = json.loads((root / 'Profiles/versions.json').read_text())['defaults']['codex']
    version = record.get('version')
    if not isinstance(version, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', version) is None:
        raise ValueError('Select a complete local Codex installation in Studio Updates.')
    path = root / 'Toolchains/Codex' / version / 'codex'
    value = installed(path)
    if (record.get('id') != version or record.get('binary') != str(path)
            or record.get('binarySha256') != value['sha256']):
        raise ValueError('The selected Codex default does not match its installed component metadata.')
    return {**value, 'toolScope': scope, 'available': True,
            'runtimeFeatures': list(feature_names(str(path), value['sha256']))}


@lru_cache(maxsize=16)
def feature_names(path, checksum):
    """Ask this binary, without a credential home, network, thread or model call."""
    args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-all']
    for directory in ('/usr', '/lib', '/lib64'):
        if Path(directory).exists(): args += ['--ro-bind', directory, directory]
    args += ['--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--dir', '/codex',
             '--dir', '/bin', '--ro-bind', path, '/bin/codex', '--chdir', '/tmp', '--clearenv',
             '--setenv', 'HOME', '/tmp', '--setenv', 'CODEX_HOME', '/codex',
             '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8',
             '/bin/codex', 'features', 'list']
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10, check=False)
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError('The selected Codex runtime could not report its feature settings.')
    lines = result.stdout.decode('utf-8').splitlines()
    features = []
    for line in lines:
        if not line.strip(): continue
        match = re.fullmatch(r'([a-z][a-z0-9_.]{0,99})\s+(.+?)\s+(true|false)', line)
        if not match:
            raise ValueError('The selected Codex runtime reported an unsupported feature-list format.')
        # Removed entries include dotted compatibility aliases, not active
        # boolean FeatureToml settings. CLI override keys are split on dots.
        if match[2].strip() == 'removed': continue
        if '.' in match[1]:
            raise ValueError('The selected Codex runtime reported a nested feature setting that cannot be overridden safely.')
        features.append(match[1])
    if not features or len(features) > 512 or len(set(features)) != len(features):
        raise ValueError('The selected Codex runtime did not report a valid feature list.')
    return tuple(sorted(features))


def supports(engine, feature):
    features = engine.get('runtimeFeatures')
    return native(engine) and isinstance(features, list) and feature in features


def options(r4os, scope):
    try:
        return selected(r4os, scope)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return {'toolScope': scope, 'version': 'unavailable', 'sha256': '', 'available': False,
                'reason': 'The selected Codex installation is missing or does not match its component metadata. Review the Codex default in Studio Updates.'}


def for_input(store, session, original=None):
    """Already accepted queues retain even legacy snapshot bytes verbatim."""
    if session['engine'].get('kind') == 'claude-code':
        return session
    if original is not None:
        engine = original['engine']
        binary(store.r4os, engine)
    else:
        from tool_catalog import tool_scope
        try: engine = selected(store.r4os, tool_scope(session))
        except subprocess.SubprocessError as error:
            raise ValueError('The selected Codex runtime could not report its feature settings.') from error
        if session['engine'].get('api'):
            engine['api'] = session['engine']['api']
    return {**session, 'engine': engine}
