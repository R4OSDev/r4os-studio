"""Installed Codex identities. Studio defaults select new work, never old receipts."""
import json
from pathlib import Path
import re


def native(engine):
    return (isinstance(engine, dict) and engine.get('kind') != 'claude-code'
            and isinstance(engine.get('version'), str)
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', engine['version']) is not None
            and isinstance(engine.get('sha256'), str)
            and re.fullmatch(r'[a-f0-9]{64}', engine['sha256']) is not None)


def installed(binary, expected=None):
    from profile import regular, digest
    binary = regular(binary)
    metadata = json.loads(regular(binary.parent / '.studio-component.json').read_text())
    version, checksum = metadata.get('version'), metadata.get('binarySha256')
    value = {'version': version, 'sha256': checksum, 'binary': str(binary), 'runtimeSelection': 1}
    if (not native(value) or binary.name != 'codex' or binary.parent.name != version
            or metadata.get('id') != version or digest(binary) != checksum):
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
    return {**value, 'toolScope': scope, 'available': True}


def options(r4os, scope):
    try:
        return selected(r4os, scope)
    except (OSError, ValueError, KeyError, TypeError):
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
        engine = selected(store.r4os, tool_scope(session))
        if session['engine'].get('api'):
            engine['api'] = session['engine']['api']
    return {**session, 'engine': engine}
