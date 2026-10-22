"""Resolve the selected SDK's published tools by identity, without version approvals."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
from common import read_url, download, unpack
from rust_sdk import verify_files, command


class Download:
    def progress(self, *args, **kwargs): pass


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(context, pinned=None):
    base = context['cache']; version = context['pins']['sdk']['version']
    url = 'https://github.com/R4OSDev/r4os-sdk/releases/download/v' + version + '/SDK-Release.json'
    saved = base / 'SDK-Release.json'
    if saved.is_symlink(): raise ValueError('Invalid SDK release metadata path.')
    raw = saved.read_bytes() if saved.exists() else read_url(url, 2 * 1024**2)
    checksum = hashlib.sha256(raw).hexdigest(); release = json.loads(raw)
    if pinned and (pinned['releaseSha256'] != checksum or pinned['url'] != url):
        raise ValueError('Pinned SDK tools metadata changed.')
    if release.get('schema') != 1 or release.get('interface') != 'r4os-sdk-release':
        raise ValueError('The SDK release metadata format is not supported.')
    for kind in ('sdk', 'contract'):
        if release[kind]['source_commit'] != context['pins'][kind]['revision']:
            raise ValueError('The selected ' + kind.upper() + ' does not match the SDK release metadata.')
    devkit = release['devkit']; package = devkit['package']; capability = release['capabilities']['package']
    for item in (package, capability):
        if not item['url'].startswith(url.rsplit('/', 1)[0] + '/'):
            raise ValueError('The SDK tools archive must belong to its selected SDK release.')
    pin = {'url': url, 'releaseSha256': checksum, 'archiveSha256': package['sha256'],
           'profileSha256': devkit['profile_sha256'], 'capabilitiesSha256': capability['sha256']}
    if pinned and pin != pinned: raise ValueError('Pinned SDK tools changed.')
    target = base / 'sdk-tools'
    if target.is_symlink(): raise ValueError('Invalid SDK tool storage.')
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.sdk-tools-', dir=base) as temporary:
            work = Path(temporary); archive = work / 'tools.tar.gz'
            download(Download(), package['url'], archive, package['sha256'], limit=64 * 1024**2)
            source = unpack(archive, work / 'unpacked', limit=256 * 1024**2)
            if digest(source / 'RustToolsProfile.json') != pin['profileSha256']:
                raise ValueError('The SDK tool profile checksum changed.')
            profile = json.loads((source / 'RustToolsProfile.json').read_text())
            verify_files(source, {v['path']: v['sha256'] for v in profile['files']})
            source.rename(target)
    if digest(target / 'RustToolsProfile.json') != pin['profileSha256']:
        raise ValueError('The SDK tool profile checksum changed.')
    profile = json.loads((target / 'RustToolsProfile.json').read_text())
    verify_files(target, {v['path']: v['sha256'] for v in profile['files']})
    for kind in ('sdk', 'contract'):
        verify_files(context['paths'][kind], {v['path']: v['sha256'] for v in profile[kind]['inputs']})
    zig = json.loads((target / 'Profile/ZigToolchain.json').read_text())
    if (zig['version'] != context['pins']['zig']['version']
        or zig['hosts']['Linux']['sha256'] != context['pins']['zig']['sha256']):
        raise ValueError('The selected compiler differs from the SDK toolchain requirement: Zig ' + zig['version'] + '.')
    catalog = target / profile['hosts']['Linux']['catalog']; catalog.chmod(0o755)
    raw_capabilities = command([catalog, 'capabilities', '--json', '--profile', target / 'RustToolsProfile.json'],
                               {'PATH': '', 'HOME': str(base)}, base)
    capabilities = json.loads(raw_capabilities)
    # Check the exact published catalog bytes separately from JSON serialization.
    cap_path = base / 'sdk-capabilities.json'
    if not cap_path.exists():
        data = read_url(capability['url'], 2 * 1024**2)
        if hashlib.sha256(data).hexdigest() != pin['capabilitiesSha256']:
            raise ValueError('The SDK capability checksum changed.')
        cap_path.write_bytes(data)
    if cap_path.is_symlink() or digest(cap_path) != pin['capabilitiesSha256'] or json.loads(cap_path.read_text()) != capabilities:
        raise ValueError('The SDK capability catalog changed.')
    if capabilities.get('schema') not in (2, 3) or capabilities.get('interface') != 'r4os-sdk-capabilities' or capabilities.get('technical'):
        raise ValueError('The SDK capability format is not supported.')
    if not saved.exists(): saved.write_bytes(raw)
    return {'tools': target, 'profile': profile, 'pin': pin, 'catalog': catalog,
            'capabilities': capabilities, 'release': release}


def combination(context, template, language):
    cap = context.get('capabilities')
    if not cap: return None
    _, _, kind, app_class, _ = template
    role = 'subsystem' if template[0] == 'subsystem' else None
    entry = 'app' if kind == 'R4X' else None
    def matches(value):
        return (value['language'] == language and value['kind'] == kind and value['app_class'] == app_class
                and value.get('role') == role and value.get('entry_mode') == entry and value['execution'] == 'host')
    support = next((v for v in cap['support'] if matches(v) and 'Linux' in v['hosts']), None)
    candidate = next((v for v in cap['templates'] if matches(v) and v['supported']), None)
    return {'supported': bool(support and support['supported'] and candidate), 'qualified': bool(support and support['supported'] and candidate),
            'template': candidate, 'reason': support['reason'] if support else 'The SDK does not declare this module type.'}


def render(context, directory, project, template):
    from sdk import validate
    match = combination(context, template, project['language'])
    if not match or not match['supported']: raise ValueError(match['reason'] if match else 'SDK templates are unavailable.')
    runner = context.get('runner')
    if not runner: raise ValueError('The SDK project creator needs the local PowerShell runner. Install the SDK Rust tools in Updates.')
    args = [runner, '-NoLogo', '-NoProfile', '-File', context['paths']['sdk'] / context['capabilities']['project_creation']['driver'],
            '-TemplateId', match['template']['id'], '-Directory', directory, '-ProjectName', project['moduleName'],
            '-SdkRoot', context['paths']['sdk'], '-ContractRoot', context['paths']['contract'], '-ToolsRoot', context['sdkTools']['tools']]
    if context.get('rust'): args += ['-InstallRoot', context['rust']['prefix'] / 'Install', '-CacheRoot', context['cache'] / 'rust-create']
    command(args, {'PATH': str(runner.parent) + ':/usr/bin:/bin', 'HOME': str(context['cache']),
                   'LANG': 'C.UTF-8', 'POWERSHELL_TELEMETRY_OPTOUT': '1'}, context['cache'])
    if project['template'] == 'subsystem':
        manifest = directory / 'module.R4MF'; lines = manifest.read_text(encoding='utf-8-sig').splitlines()
        lines = [v for v in lines if not v.startswith(('SUBSYSTEM_ID=', 'SUBSYSTEM_DISPLAY_NAME=', 'GUEST_FORMAT=', 'GUEST_EXTENSION=', 'GUEST_MAGIC=', 'GUEST_FEATURE=', 'TARGET='))]
        lines += ['SUBSYSTEM_ID=studio.' + project['id'], 'SUBSYSTEM_DISPLAY_NAME=' + project['name']]
        lines += ['GUEST_FORMAT=' + value for value in project['guestFormats']]
        lines += ['TARGET=/R4OS/SUBSYSTEMS/studio.' + project['id'] + '/' + project['moduleName'] + '.R4X']
        manifest.write_text('\n'.join(lines) + '\n')
    for name in ('LICENSE', 'NOTICE'):
        if (context['paths']['sdk'] / name).is_file(): shutil.copyfile(context['paths']['sdk'] / name, directory / (name + '.R4OS-SDK'))
    (directory / 'THIRD_PARTY_NOTICES.md').write_text('Created from the official SDK template at ' + context['pins']['sdk']['revision'] + '.\n')
    return validate(context, directory)
