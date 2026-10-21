"""Bounded official HTTPS downloads and safe, immutable archive publication."""
import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import urllib.parse
import urllib.request

HOSTS = {'github.com', 'api.github.com', 'codeload.github.com', 'raw.githubusercontent.com',
         'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
         'ziglang.org', 'static.rust-lang.org', 'download.qemu.org', 'www.qemu.org', 'keys.openpgp.org'}


def safe_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('The download source is not an approved official HTTPS host.')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return super().redirect_request(request, fp, code, message, headers, safe_url(new_url))


def open_url(url):
    return urllib.request.build_opener(Redirect()).open(urllib.request.Request(safe_url(url), headers={
        'User-Agent': 'R4OS-Studio-Components', 'Accept': 'application/json' if 'api.github.com' in url else '*/*',
    }), timeout=60)


def read_url(url, limit=8 * 1024 * 1024):
    with open_url(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Official version metadata exceeds its size limit.')
    return data


def download(manager, url, target, expected=None, limit=3 * 1024**3):
    hashed = hashlib.sha256()
    received = 0
    with open_url(url) as source, Path(target).open('xb') as output:
        total = int(source.headers.get('Content-Length') or 0)
        if total > limit:
            raise ValueError('Download exceeds its size limit.')
        while block := source.read(1024 * 1024):
            received += len(block)
            if received > limit:
                raise ValueError('Download exceeds its size limit.')
            output.write(block)
            hashed.update(block)
            manager.progress('Downloading official archive…', received=received, total=total)
        output.flush()
        os.fsync(output.fileno())
    actual = hashed.hexdigest()
    if expected and actual != expected.removeprefix('sha256:'):
        raise ValueError('The downloaded archive SHA-256 does not match its published checksum.')
    return actual


def unpack(archive, target, limit=2 * 1024**3, exclude=()):
    target = Path(target)
    target.mkdir()
    with tarfile.open(archive, 'r:*') as package:
        members = package.getmembers()
        if len(members) > 200_000 or sum(value.size for value in members) > limit:
            raise ValueError('Archive exceeds its extraction limits.')
        selected = [member for member in members if member.name.partition('/')[2] not in exclude]
        package.extractall(target, members=selected, filter='data')
    entries = list(target.iterdir())
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else target


def publish(source, target):
    source, target = Path(source), Path(target)
    if target.exists():
        raise ValueError('This component version already exists and will not be overwritten.')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Work directories are placed on the same data filesystem; rename is atomic.
    source.rename(target)
    descriptor = os.open(target.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
