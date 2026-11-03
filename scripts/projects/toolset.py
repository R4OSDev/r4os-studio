"""Resolve the selected SDK's published tools by identity, without version approvals."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
from common import read_url, download, unpack
from sdk_host import command
from sdk_metadata import capabilities_package


class Download:
    def progress(self, *args, **kwargs): pass


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(context, pinned=None, verify_components=True):
    tools = context.get('sdkTools')
    if not tools or pinned and tools['pin'] != pinned:
        raise ValueError('The project needs its verified SDK package. No legacy tool fallback is available.')
    return tools


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
    context['pins']['sdkProfile']['templateId'] = match['template']['id']
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
