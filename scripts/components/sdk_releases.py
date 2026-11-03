"""SDK updates come from published releases, never unreleased package history."""
import json
import re
import os

from common import read_url
from service import run
from sdk_sets import resolve

REPOSITORY = 'https://github.com/R4OSDev/r4os-sdk'
API = 'https://api.github.com/repos/R4OSDev/r4os-sdk/releases'
TAG = re.compile(r'^v(\d+\.\d+\.\d+)$')


def published():
    releases = {}
    for page in (1, 2):
        rows = json.loads(read_url(API + f'?per_page=100&page={page}'))
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('The official SDK release list is invalid.')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('The official SDK release metadata is invalid.')
            tag = row.get('tag_name')
            match = TAG.fullmatch(tag) if isinstance(tag, str) else None
            if not match or row.get('draft') is not False or row.get('prerelease') is not False:
                continue
            assets = row.get('assets')
            if not isinstance(assets, list):
                raise ValueError('The SDK release has invalid asset metadata.')
            manifests = [asset for asset in assets if isinstance(asset, dict) and asset.get('name') == 'SDK-Release.json']
            url = REPOSITORY + '/releases/download/' + tag + '/SDK-Release.json'
            if len(manifests) > 1 or manifests and (manifests[0].get('browser_download_url') != url
                    or type(manifests[0].get('size')) is not int or not 0 < manifests[0]['size'] <= 2 * 1024 * 1024
                    or manifests[0].get('state') != 'uploaded'):
                raise ValueError('The published SDK manifest asset is invalid.')
            if tag in releases:
                raise ValueError('The official SDK release list contains duplicate tags.')
            releases[tag] = {'version': match[1], 'tag': tag, 'manifestPublished': bool(manifests), 'published': True}
        if len(rows) < 100:
            break
    return sorted(releases.values(), key=lambda value: tuple(map(int, value['version'].split('.'))), reverse=True)


class SdkReleases:
    def catalog(self, manager, kind, older):
        if kind != 'sdk':
            raise ValueError('Invalid SDK release request.')
        releases = published()
        if not releases:
            return {'versions': [], 'latestId': None, 'hasMore': False, 'sdkReleases': {}}
        manager.progress('Reading published SDK release tags…')
        environment = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                       'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/bin/false'}
        # Only refs are read. No retained SDK Git history can restore retired
        # source revisions or become another package/SDK policy authority.
        output = run(['/usr/bin/git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                      '-c', 'protocol.file.allow=never', 'ls-remote', '--tags', REPOSITORY + '.git'], env=environment)
        refs = {}
        for line in output.splitlines():
            match = re.fullmatch(r'([a-f0-9]{40})\s+refs/tags/(v\d+\.\d+\.\d+)(\^\{\})?', line)
            if match:
                refs[match[2] + ('^{}' if match[3] else '')] = match[1]
        previous = manager.catalogs.get('sdk', {}).get('versions', [])
        limit = min(len(previous) + 10 if older else 10, 200)
        values, metadata = [], {}
        for release in releases[:limit + 1]:
            tag = release['tag']
            revision = refs.get(tag + '^{}') or refs.get(tag)
            if not revision:
                raise ValueError('The published SDK release tag could not be resolved: ' + tag)
            metadata[revision] = release.copy()
            if not release['manifestPublished']:
                metadata[revision]['reason'] = 'This release has no SDK package manifest.'
                continue
            selected = {'id': revision, 'revision': revision, 'version': release['version'],
                        'sourceUrl': REPOSITORY + '/tree/' + revision, 'sdkRelease': release}
            try:
                resolved = resolve(manager, selected)
            except (ValueError, KeyError, TypeError) as error:
                metadata[revision]['reason'] = str(error)[:500]
                continue
            part = resolved['components']['sdk']
            selected.update(archiveUrl=part['url'], sha256=part['sha256'])
            values.append(selected)
        return {'versions': values[:limit], 'latestId': values[0]['id'] if values else None,
                'hasMore': len(releases) > limit, 'sdkReleases': metadata}
