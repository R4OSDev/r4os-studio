#!/usr/bin/env python3
"""Import a checksum-verified Full release without building R4OS from source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import tempfile
import urllib.request
import zipfile

APP = Path(__file__).resolve().parent.parent
API = 'https://api.github.com/repos/R4OSDev/r4os-distribution/releases/'


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'R4OS-Studio'}), timeout=60)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', help='Release version, e.g. 0.84.47; defaults to latest stable.')
    parser.add_argument('--archive', type=Path, help='Use a previously downloaded official ZIP; still verify its published checksum.')
    args = parser.parse_args()
    release = json.load(request(API + ('tags/v' + args.version if args.version else 'latest')))
    if release['draft'] or release['prerelease']:
        raise ValueError('Only stable published releases are accepted.')
    version = release['tag_name'].removeprefix('v')
    if len(version.split('.')) != 3 or not all(v.isdigit() for v in version.split('.')):
        raise ValueError('Unexpected release version.')
    assets = {asset['name']: asset['browser_download_url'] for asset in release['assets']}
    name = f'R4OS-{version}-full-x86_64.zip'
    checksums = request(assets['SHA256SUMS.txt']).read().decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1] == name)
    root = APP / 'Data/R4OS/Images'
    root.mkdir(parents=True, exist_ok=True)
    image_id = version + '-full'
    destination = root / image_id
    if destination.exists():
        raise ValueError(f'{destination} already exists; existing images are never overwritten.')
    with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        staging = Path(temporary)
        archive = args.archive.resolve() if args.archive else staging / name
        if not args.archive:
            print(f'Downloading {name}...', flush=True)
            with request(assets[name]) as source, archive.open('wb') as output:
                shutil.copyfileobj(source, output)
        if digest(archive) != expected:
            raise ValueError('Release ZIP checksum mismatch.')
        image = staging / 'image'
        image.mkdir()
        with zipfile.ZipFile(archive) as package:
            manifest = json.loads(package.read('manifest.json'))
            disk_record = next(f for f in manifest['files'] if f['path'] == 'disk.img')
            for entry in package.infolist():
                path = Path(entry.filename)
                if path.is_absolute() or '..' in path.parts or entry.file_size > 64 * 1024**3:
                    raise ValueError('Unsafe release archive.')
                if entry.is_dir():
                    continue
                target = image / 'disk.img' if entry.filename == 'disk.img' else image / 'release' / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open('wb') as output:
                    if entry.filename == 'disk.img':
                        while block := source.read(1024 * 1024):
                            if block.count(0) == len(block):
                                output.seek(len(block), 1)
                            else:
                                output.write(block)
                        output.truncate(entry.file_size)
                    else:
                        shutil.copyfileobj(source, output)
        print('Verifying extracted disk...', flush=True)
        disk = image / 'disk.img'
        actual = digest(disk)
        if actual != disk_record['sha256'] or disk.stat().st_size != disk_record['bytes']:
            raise ValueError('Extracted disk checksum/size mismatch.')
        stat = disk.stat()
        metadata = {'schema': 1, 'id': image_id, 'version': version, 'variant': 'full',
                    'architecture': 'x86_64', 'disk': 'disk.img', 'sha256': actual,
                    'archiveSha256': expected, 'sourceUrl': assets[name],
                    'diskSizeBytes': stat.st_size, 'diskMtimeMs': int(stat.st_mtime * 1000)}
        (image / 'image.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (image / 'release/SHA256SUMS.txt').write_text(checksums)
        if os.geteuid() == 0:
            user = pwd.getpwnam('r4os-studio')
            for path in [image, *image.rglob('*')]:
                os.chown(path, user.pw_uid, user.pw_gid)
        for path in [image, *image.rglob('*')]:
            path.chmod(0o500 if path.is_dir() else 0o400)
        image.rename(destination)
        print(f'Imported: {destination}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Image import failed: {error}') from error
