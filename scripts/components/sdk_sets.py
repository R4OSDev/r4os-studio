"""Exact SDK/Contract/Libraries identities from official, bounded release metadata.

Reading status never fetches metadata or changes the active component profile.
Archive SHA-256 values describe release archives, not existing codeload installs.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.error import HTTPError

from common import read_url
import sdk_package
from service import atomic

PARTS = ('sdk', 'contract', 'libraries')
MAX_MANIFEST = 2 * 1024 * 1024
REVISION = re.compile(r'^[a-f0-9]{40}$')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')


def profile_revision(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def regular_json(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Invalid SDK metadata file.')
        value = stream.read(limit + 1)
        if len(value) > limit:
            raise ValueError('SDK metadata exceeds its size limit.')
    return json.loads(value)


def cache_path(manager, selected):
    identity = selected.get('revision', selected.get('id', ''))
    if not isinstance(identity, str) or not REVISION.fullmatch(identity) or identity != selected.get('id'):
        raise ValueError('The SDK needs an exact source revision.')
    folder = manager.root / 'Profiles/SDK-Sets'
    if folder.is_symlink() or (folder.exists() and folder.resolve() != folder):
        raise ValueError('Invalid SDK metadata cache directory.')
    return folder / (identity + '.json')


def manifest_url(selected):
    version = selected.get('version', '')
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError('Invalid SDK release version.')
    return f'https://github.com/R4OSDev/r4os-sdk/releases/download/v{version}/SDK-Release.json'


def parse_manifest(selected, raw):
    document = sdk_package.manifest(raw, selected.get('version'), selected.get('revision', selected.get('id')))
    result = sdk_package.summary(document, raw)
    pin = selected.get('dependencies', {}).get('contract')
    contract = result['components']['contract']
    if pin and (pin['revision'] != contract['revision'] or pin['packageHash'] != contract['packageHash']):
        raise ValueError('The SDK package Contract differs from its source dependency.')
    return result


def resolve(manager, selected, fetch=True):
    path = cache_path(manager, selected)
    url = manifest_url(selected)
    if path.exists() or path.is_symlink():
        saved = regular_json(path, 3 * MAX_MANIFEST)
        if saved.get('schema') != 1 or saved.get('sdkId') != selected['id'] or saved.get('url') != url:
            raise ValueError('The cached SDK release identity is invalid.')
        raw = base64.b64decode(saved['body'], validate=True)
        if hashlib.sha256(raw).hexdigest() != saved.get('sha256'):
            raise ValueError('The cached SDK release checksum is invalid.')
    elif fetch:
        release = selected.get('sdkRelease')
        if release is not None and not release.get('published'):
            raise ValueError('No published SDK package set was found for this local source revision. Existing project pins are retained.')
        if release is not None and not release.get('manifestPublished'):
            raise ValueError('This SDK release does not publish SDK-Release.json. Existing project pins are retained.')
        try:
            raw = read_url(url, MAX_MANIFEST)
        except HTTPError as error:
            if error.code != 404:
                raise
            raise ValueError('SDK-Release.json is not available for this version. Check published SDK releases again; existing installations and project pins are retained.') from None
        result = parse_manifest(selected, raw)
        sums = read_url(url.removesuffix('SDK-Release.json') + 'SHA256SUMS.txt', 65536)
        sdk_package.checksums(sums, raw, sdk_package.decode(raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, {'schema': 1, 'sdkId': selected['id'], 'url': url,
                      'sha256': result['manifestSha256'], 'body': base64.b64encode(raw).decode('ascii'),
                      'checksumsBody': base64.b64encode(sums).decode('ascii')})
        return result
    else:
        return {'state': 'unresolved', 'reason': 'Check SDK versions to resolve the matching packages.'}
    result = parse_manifest(selected, raw)
    if not isinstance(saved.get('checksumsBody'), str):
        raise ValueError('The SDK package checksum binding is missing. Check this SDK release again.')
    sdk_package.checksums(base64.b64decode(saved['checksumsBody'], validate=True), raw, sdk_package.decode(raw))
    return result


def summary(value, installed, defaults):
    result = copy.deepcopy(value)
    if result['state'] != 'ready':
        return result
    for kind, part in result['components'].items():
        part['installed'] = any(record['id'] == part['revision'] and record['version'] == part['version']
                                for record in installed[kind])
        active = defaults.get(kind, {})
        part['active'] = active.get('id') == part['revision'] and active.get('version') == part['version']
    result['complete'] = all(part['installed'] for part in result['components'].values())
    result['active'] = result['complete'] and all(part['active'] for part in result['components'].values())
    return result
