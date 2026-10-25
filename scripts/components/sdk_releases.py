"""SDK updates come from published releases, never unreleased package history."""
import json
import re

from common import read_url
from packages import git, record, source_repository

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
        repository = source_repository(manager, 'sdk', fetch_main=False)
        manager.progress('Reading published SDK release tags…')
        # One remote tag read covers lightweight and annotated/peeled tags.
        # target_commitish may be a moving branch and is never a source pin.
        refs = {}
        for line in git(repository, 'ls-remote', '--tags', 'origin').splitlines():
            match = re.fullmatch(r'([a-f0-9]{40})\s+refs/tags/(v\d+\.\d+\.\d+)(\^\{\})?', line)
            if match:
                refs[match[2] + ('^{}' if match[3] else '')] = match[1]
        previous = manager.catalogs.get('sdk', {}).get('versions', [])
        limit = min(len(previous) + 10 if older else 10, 200)
        values, metadata = [], {}
        for release in releases:
            tag = release['tag']
            revision = refs.get(tag + '^{}') or refs.get(tag)
            if not revision:
                raise ValueError('The published SDK release tag could not be resolved: ' + tag)
            metadata[revision] = release
            if len(values) >= limit + 1:
                continue
            # Releases on another branch may not be present in the main cache.
            try:
                git(repository, 'cat-file', '-e', revision + '^{commit}')
            except ValueError:
                git(repository, 'fetch', '--filter=blob:none', 'origin', 'refs/tags/' + tag)
            value = record(repository, 'sdk', revision)
            if value['version'] != release['version']:
                raise ValueError('The SDK release tag contradicts its package version: ' + tag)
            values.append(value)
        return {'versions': values[:limit], 'latestId': values[0]['id'] if values else None,
                'hasMore': len(values) > limit, 'sdkReleases': metadata}
