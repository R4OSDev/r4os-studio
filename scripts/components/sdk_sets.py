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
    if len(raw) > MAX_MANIFEST:
        raise ValueError('SDK release metadata exceeds its size limit.')
    document = json.loads(raw)
    if (not isinstance(document, dict) or type(document.get('schema')) is not int
            or document['schema'] != 1 or document.get('interface') != 'r4os-sdk-release'):
        raise ValueError('This SDK release uses unsupported release metadata.')
    result = {'state': 'ready', 'manifestUrl': manifest_url(selected),
              'manifestSha256': hashlib.sha256(raw).hexdigest(), 'components': {}}
    release_prefix = result['manifestUrl'].removesuffix('SDK-Release.json')
    # Legacy releases may contain SDK/Contract metadata without a Libraries
    # package. They cannot form a combined set; existing pins remain usable.
    if not isinstance(document.get('libraries'), dict):
        raise ValueError('This SDK release does not declare a Libraries package for combined selection. Existing project pins are retained.')
    for kind in PARTS:
        part = document.get(kind)
        if not isinstance(part, dict):
            raise ValueError(f'The SDK release does not declare an exact {kind} package.')
        version, revision, package = part.get('package_version'), part.get('source_commit'), part.get('package')
        if (not isinstance(version, str) or not VERSION.fullmatch(version)
                or not isinstance(revision, str) or not REVISION.fullmatch(revision)
                or not isinstance(package, dict)):
            raise ValueError(f'The SDK release has invalid {kind} package identities.')
        source = f'https://github.com/R4OSDev/r4os-{kind}/tree/{revision}'
        filename, sha, size = package.get('file'), package.get('sha256'), package.get('bytes')
        if (part.get('source_url') != source or part.get('archive_prefix') != kind.upper() + '/'
                or not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.tar\.gz', filename)
                or package.get('url') != release_prefix + filename
                or not isinstance(sha, str) or not SHA256.fullmatch(sha)
                or type(size) is not int or not 0 < size <= 3 * 1024**3):
            raise ValueError(f'The SDK release has invalid {kind} archive metadata.')
        result['components'][kind] = {'version': version, 'revision': revision, 'sourceUrl': source,
                                      'url': package['url'], 'sha256': sha, 'bytes': size}
    sdk = result['components']['sdk']
    if sdk['revision'] != selected['id'] or sdk['version'] != selected['version']:
        raise ValueError('SDK release metadata does not match the selected source revision and version.')
    pin = selected.get('dependencies', {}).get('contract')
    if (not pin or pin.get('revision') != result['components']['contract']['revision']
            or not isinstance(pin.get('packageHash'), str) or not pin['packageHash']):
        raise ValueError('SDK release metadata contradicts or omits the SDK Contract source pin.')
    result['components']['contract']['packageHash'] = pin['packageHash']
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
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, {'schema': 1, 'sdkId': selected['id'], 'url': url,
                      'sha256': result['manifestSha256'], 'body': base64.b64encode(raw).decode('ascii')})
        return result
    else:
        return {'state': 'unresolved', 'reason': 'Check SDK versions to resolve the matching packages.'}
    return parse_manifest(selected, raw)


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
