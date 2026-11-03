"""The SDK owns profile policy; Studio binds its original package and receipts.

This module validates transport identities and cross-file bindings. Profile
resolution, source trees and derived policy are validated by the SDK tools.
There is deliberately no reader for the retired DevKit release interface.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

SCHEMA = 1
INTERFACE = 'r4os-sdk-package'
MAX_METADATA = 2 * 1024**2
SHA256 = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')
VERSION = re.compile(r'\d+\.\d+\.\d+')
IDENTIFIER = re.compile(r'[a-z][a-z0-9_-]{0,95}')
PROFILE_FILES = {name: 'Profiles/' + name + '.json' for name in ('Build', 'Tools', 'Components')}
SOURCE_ROLES = {'sdk': 'sdk-source', 'contract': 'contract-source', 'libraries': 'libraries-source'}
REQUIRED_ROLES = {*SOURCE_ROLES.values(), 'recovery-sources', 'tools', 'capabilities', 'qualification'}


def fail(message):
    raise ValueError('The SDK package ' + message + ' No legacy fallback is available.')


def unique_object(pairs):
    result, folded = {}, set()
    for key, value in pairs:
        if key.casefold() in folded:
            fail('contains duplicate or case-conflicting JSON keys.')
        result[key] = value
        folded.add(key.casefold())
    return result


def decode(raw):
    if len(raw) > MAX_METADATA:
        fail('metadata exceeds the size limit.')
    def invalid_constant(_):
        fail('contains a non-JSON number.')
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def regular_bytes(path, limit=MAX_METADATA):
    path = Path(path)
    if path.absolute() != path.resolve(strict=True):
        fail('contains an indirect metadata path.')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            fail('metadata is not a bounded regular file.')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        fail('metadata exceeds the size limit.')
    return raw


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or PurePosixPath(value).is_absolute() or any(p in ('', '.', '..') for p in value.split('/'))):
        fail('contains an invalid relative path.')
    return value


def release_url(version):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        fail('has an invalid release version.')
    return 'https://github.com/R4OSDev/r4os-sdk/releases/download/v' + version + '/SDK-Release.json'


def manifest(raw, version, revision):
    document = decode(raw)
    if (not isinstance(document, dict) or type(document.get('schema')) is not int
            or document['schema'] != SCHEMA or document.get('interface') != INTERFACE):
        fail('requires SDK-Release.json schema 1 / r4os-sdk-package.')
    if document.get('sdk_version') != version:
        fail('version contradicts the selected release.')
    source = document.get('sdk_source', {})
    if (not isinstance(revision, str) or not COMMIT.fullmatch(revision)
            or source.get('repository') != 'https://github.com/R4OSDev/r4os-sdk.git'
            or source.get('commit') != revision or not SHA256.fullmatch(source.get('tree_sha256', ''))
            or document.get('source_hash_mode') != 'r4os-files-sha256-lf-v1'):
        fail('source identity contradicts the selected release.')
    refs = document.get('profile_sources')
    if not isinstance(refs, dict) or set(refs) != set(PROFILE_FILES):
        fail('must bind exactly the three canonical profile sources.')
    for name, path in PROFILE_FILES.items():
        ref = refs[name]
        if (not isinstance(ref, dict) or type(ref.get('schema')) is not int or ref['schema'] != 1
                or ref.get('path') != path or not SHA256.fullmatch(ref.get('sha256', ''))):
            fail('has an invalid ' + name + ' profile source.')
    assets = document.get('assets')
    if not isinstance(assets, list) or not 7 <= len(assets) <= 32:
        fail('has no complete bounded asset set.')
    names, roles = set(), {}
    prefix = release_url(version).removesuffix('SDK-Release.json')
    for item in assets:
        if not isinstance(item, dict):
            fail('has invalid asset metadata.')
        name, role = relative(item.get('path')), item.get('role')
        if ('/' in name or name.casefold() in names or not isinstance(role, str)
                or not IDENTIFIER.fullmatch(role) or role in roles
                or item.get('url') != prefix + name or not SHA256.fullmatch(item.get('sha256', ''))
                or type(item.get('bytes')) is not int or not 0 < item['bytes'] <= 3 * 1024**3):
            fail('has ambiguous or invalid official asset identities.')
        if 'prefix' in item:
            relative(item['prefix'])
        names.add(name.casefold())
        roles[role] = item
    if not REQUIRED_ROLES.issubset(roles):
        fail('is missing required source, tools or evidence assets.')
    if any('prefix' not in roles[role] for role in (*SOURCE_ROLES.values(), 'recovery-sources', 'tools')):
        fail('does not declare source and tools archive prefixes.')
    for kind in ('contract', 'libraries'):
        item = document.get('sources', {}).get(kind, {})
        if (item.get('repository') != 'https://github.com/R4OSDev/r4os-' + kind + '.git'
                or not COMMIT.fullmatch(item.get('commit', '')) or not VERSION.fullmatch(item.get('version', ''))
                or not isinstance(item.get('zig_hash'), str) or not item['zig_hash']):
            fail('has an invalid ' + kind + ' source binding.')
    return document


def asset(document, role):
    matches = [value for value in document['assets'] if value['role'] == role]
    if len(matches) != 1:
        fail('does not identify exactly one ' + role + ' asset.')
    return matches[0]


def profile_hashes(document):
    return {name: document['profile_sources'][name]['sha256'] for name in PROFILE_FILES}


def checksums(raw, manifest_raw, document):
    if len(raw) > 65536:
        fail('checksum list exceeds the size limit.')
    entries, folded = {}, set()
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *]([A-Za-z0-9_.+-]+)', line)
        if not match or match[2].casefold() in folded:
            fail('has an invalid or duplicate checksum entry.')
        entries[match[2]] = match[1]
        folded.add(match[2].casefold())
    if entries.get('SDK-Release.json') != sha256(manifest_raw):
        fail('manifest does not match the published checksum list.')
    for item in document['assets']:
        if entries.get(item['path']) != item['sha256']:
            fail('asset identity contradicts the published checksum list.')
    return entries


def profiles(sdk_root, document, capability_raw=None):
    """Check original bytes/references, never resolve a policy in Studio."""
    values = {}
    for name, path in PROFILE_FILES.items():
        raw = regular_bytes(Path(sdk_root) / path)
        if sha256(raw) != document['profile_sources'][name]['sha256']:
            fail('original ' + name + ' profile checksum changed.')
        value = decode(raw)
        if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
            fail('original ' + name + ' profile uses an unsupported schema.')
        values[name] = value
    build, tools, components = (values[name] for name in PROFILE_FILES)
    for owner, key in ((build, 'profiles'), (build, 'codegen'), (build, 'cpu_baselines'),
                       (tools, 'toolsets'), (tools, 'tools'), (components, 'sets')):
        entries = owner.get(key)
        if not isinstance(entries, dict) or not entries or any(not IDENTIFIER.fullmatch(k) for k in entries):
            fail('has invalid identifiers in ' + key + '.')
    for item in build['profiles'].values():
        if (not isinstance(item, dict) or item.get('codegen') not in build['codegen']
                or item.get('toolset') not in tools['toolsets'] or item.get('components') not in components['sets']
                or 'cpu' in item and item['cpu'] not in build['cpu_baselines']):
            fail('has an unresolved build profile reference.')
    for item in tools['toolsets'].values():
        if (not isinstance(item, dict) or not isinstance(item.get('tools'), list)
                or any(key not in tools['tools'] for key in item['tools'])):
            fail('has an unresolved toolset reference.')
    for key, original in (('profiles', build['profiles']), ('tools', tools['tools']),
                          ('toolsets', tools['toolsets']), ('component_sets', components.get('sets')),
                          ('sources', components.get('repositories')), ('system_libraries', components.get('libraries')),
                          ('policy', components.get('policy'))):
        if document.get(key) != original:
            fail('release projection contradicts original ' + key + '.')
    if capability_raw is not None:
        entry = asset(document, 'capabilities')
        if len(capability_raw) != entry['bytes'] or sha256(capability_raw) != entry['sha256']:
            fail('capability asset checksum changed.')
        capability = decode(capability_raw)
        if (type(capability.get('schema')) is not int or capability['schema'] != 3
                or capability.get('interface') != 'r4os-sdk-capabilities'
                or capability.get('profile_sources') != profile_hashes(document)
                or capability.get('package_interface') != INTERFACE):
            fail('capability schema or original profile binding changed.')
    return values


def summary(document, raw):
    """A display projection, not a replacement for the native SDK resolver."""
    parts = {}
    for kind, role in SOURCE_ROLES.items():
        item = asset(document, role)
        source = document['sdk_source'] if kind == 'sdk' else document['sources'][kind]
        version = document['sdk_version'] if kind == 'sdk' else source['version']
        revision = source['commit']
        parts[kind] = {'version': version, 'revision': revision,
                       'sourceUrl': 'https://github.com/R4OSDev/r4os-' + kind + '/tree/' + revision,
                       'url': item['url'], 'sha256': item['sha256'], 'bytes': item['bytes']}
        if kind != 'sdk':
            parts[kind]['packageHash'] = source['zig_hash']
    return {'state': 'ready', 'interface': INTERFACE, 'manifestUrl': release_url(document['sdk_version']),
            'manifestSha256': sha256(raw), 'profileSources': profile_hashes(document),
            'buildProfiles': document['profiles'], 'toolsets': document['toolsets'],
            'componentSets': document['component_sets'], 'components': parts}
