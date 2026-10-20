"""Verified R4OS Full releases share the same local inventory as virtual machines."""
import json
from pathlib import Path
import re
import sys
import tempfile

from common import download, read_url
from service import run

API = 'https://api.github.com/repos/R4OSDev/r4os-distribution/releases'


def asset_for(release):
    version = release['tag_name'].removeprefix('v')
    if release['draft'] or release['prerelease'] or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        return None
    expected = f'R4OS-{version}-full-x86_64.zip'.lower()
    asset = next((item for item in release['assets'] if item['name'].lower() == expected), None)
    if not asset:
        return None
    checksum = asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', checksum):
        checksums = next((item for item in release['assets'] if item['name'] == 'SHA256SUMS.txt'), None)
        if not checksums:
            return None
        lines = read_url(checksums['browser_download_url'], 1024 * 1024).decode().splitlines()
        checksum = next((line.split()[0] for line in lines if len(line.split()) == 2 and line.split()[1].lstrip('*') == asset['name']), '')
    checksum = checksum.removeprefix('sha256:')
    if not re.fullmatch('[a-f0-9]{64}', checksum):
        return None
    return {'id': version + '-full', 'version': version, 'sha256': checksum,
            'sourceUrl': release['html_url'], 'archiveUrl': asset['browser_download_url']}


class Releases:
    def catalog(self, manager, kind, older):
        limit = len(manager.catalogs.get(kind, {}).get('versions', [])) + 10 if older else 10
        values = {}
        page = 1
        more = False
        while True:
            releases = json.loads(read_url(API + f'?per_page=100&page={page}'))
            for release in releases:
                value = asset_for(release)
                if value:
                    values[value['id']] = value
            more = len(releases) == 100
            if len(values) > limit or not more:
                break
            page += 1
        versions = sorted(values.values(), key=lambda item: tuple(map(int, item['version'].split('.'))), reverse=True)
        return {'versions': versions[:limit], 'latestId': versions[0]['id'] if versions else None,
                'hasMore': more or len(versions) > limit}

    def install(self, manager, kind, record):
        release = json.loads(read_url(API + '/tags/v' + record['version']))
        verified = asset_for(release)
        if not verified or verified != record:
            raise ValueError('The selected release archive changed. Check versions again.')
        root = manager.root / 'Images'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary:
            archive = Path(temporary) / 'release.zip'
            download(manager, record['archiveUrl'], archive, record['sha256'])
            manager.progress('Importing and verifying the complete R4OS disk image…', received=0, total=0)
            script = Path(__file__).resolve().parent.parent / 'import-r4os-image.py'
            run([sys.executable, '-B', str(script), '--version', record['version'], '--archive', str(archive),
                 '--r4os-dir', str(manager.root), '--expected-archive-sha256', record['sha256']], timeout=900)
