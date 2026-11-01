"""Canonical identities for both published SDK release metadata layouts."""
import re


def component_source_url(part, kind):
    revision = part.get('source_commit') if isinstance(part, dict) else None
    if (kind not in ('sdk', 'contract', 'libraries') or not isinstance(revision, str)
            or not re.fullmatch(r'[a-f0-9]{40}', revision)):
        raise ValueError('The SDK release has invalid component source metadata.')
    url = f'https://github.com/R4OSDev/r4os-{kind}/tree/{revision}'
    if part.get('source_url', url) != url:
        raise ValueError('The SDK release has contradictory component source metadata.')
    return url


def capabilities_package(release, manifest_url):
    """Read the nested package or direct file/hash/size without changing raw bytes."""
    if not isinstance(manifest_url, str) or not re.fullmatch(
            r'https://github\.com/R4OSDev/r4os-sdk/releases/download/v\d+\.\d+\.\d+/SDK-Release\.json', manifest_url):
        raise ValueError('The SDK capability asset needs an exact official release URL.')
    section = release.get('capabilities') if isinstance(release, dict) else None
    if not isinstance(section, dict):
        raise ValueError('The SDK release has invalid capability asset metadata.')
    nested = 'package' in section
    item = section['package'] if nested else section
    if not isinstance(item, dict):
        raise ValueError('The SDK release has invalid capability asset metadata.')
    filename, sha, size = item.get('file'), item.get('sha256'), item.get('bytes')
    if (not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.json', filename)
            or not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha)
            or type(size) is not int or not 0 < size <= 2 * 1024**2):
        raise ValueError('The SDK release has invalid capability asset metadata.')
    url = manifest_url.removesuffix('SDK-Release.json') + filename
    if item.get('url', None if nested else url) != url:
        raise ValueError('The SDK capability asset must belong to its selected release.')
    result = {'file': filename, 'url': url, 'sha256': sha, 'bytes': size}
    if nested and any(key in section and section[key] != value for key, value in result.items()):
        raise ValueError('The SDK release has contradictory capability asset metadata.')
    return result
