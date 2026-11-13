"""Resolve managed REA's local filesystem arguments in the selected workspace."""

from skill_mcp_client import McpFault
from workspace_context import Workspace


INPUT_DIRECTORIES = ('working_directory',)
INPUT_PATHS = {
    'analyze_javascript_application': ('input_path',),
    'capture_electron_scenario': ('application_path', 'executable_path'),
    'compare_bundles': ('left_bundle_path', 'right_bundle_path'),
    'compare_javascript_export_shapes': ('left_module_path', 'right_module_path'),
    'export_environment_bundle': ('package_tarball',),
    'export_web_scripts': ('capture_path',),
    'inspect_android_class': ('mapping_path',),
    'inspect_android_jni_bindings': ('library_paths',),
    'inspect_android_method': ('mapping_path',),
    'inspect_il2cpp_metadata': ('binary_path',),
    'inspect_web_network_capture': ('capture_path',),
    'inspect_wasm_artifact': ('glue_paths', 'candidate_paths'),
    'open_binary': ('snapshot_path',),
    'recover_javascript_sources': ('additional_paths',),
    'trace_web_module_imports': ('manifest_path',),
    'trace_web_source_location': ('manifest_path',),
}

OUTPUT_PATHS = {
    'close_binary': ('snapshot_path',),
    'decompile_all': ('output_directory',),
    'export_environment_bundle': ('output_directory',),
    'export_evidence_bundle': ('path',),
    'export_web_scripts': ('output_directory',),
    'extract_firmware': ('output_directory',),
    'recover_javascript_sources': ('output_directory',),
    'reset_investigation': ('save_path',),
}

LOCAL_INPUT = ('local filesystem path', 'absolute filesystem path', 'absolute path',
               'absolute local path', 'absolute local filesystem path', 'absolute local capture path', 'absolute local recording path',
               'absolute selected local', 'selected local', 'explicit absolute managed pe/cli path')


class TargetUnavailable(McpFault):
    request_not_sent = True


def resolve(worker, state, tool, arguments):
    if not isinstance(arguments, dict) or not isinstance(tool, dict):
        return arguments
    name = tool['name']
    fields = tool.get('inputSchema', {}).get('properties', {})
    outputs = OUTPUT_PATHS.get(name, ())
    inputs = INPUT_PATHS.get(name, ())
    path = fields.get('path', {})
    if (path.get('type') == 'string' and 'path' not in outputs
            and path.get('description', '').casefold().startswith(LOCAL_INPUT)):
        inputs = (*inputs, 'path')
    inputs = (*inputs, *(field for field in INPUT_DIRECTORIES if field in fields))
    working = Workspace(worker.store.workspace, {'/session': state / 'Data'})

    def path_value(value, field, output):
        if not isinstance(value, str) or not value or '\0' in value:
            return value
        if value == '/attachments' or value.startswith('/attachments/'):
            from attachment_files import mounts
            from store import ProjectFault
            try:
                paths = {alias: real for real, alias in mounts(worker)}
            except ProjectFault as error:
                raise TargetUnavailable(str(error)) from None
            path = paths.get(value)
            if output or path is None:
                raise TargetUnavailable(f'REA {name}.{field}: no accepted input attachment at {value[:300]}.')
            return path
        resolved = working.path(value)
        exists = resolved.parent.is_dir() if output else resolved.exists()
        if not exists:
            where = 'parent directory of ' if output else ''
            raise TargetUnavailable(f'REA {name}.{field}: {where}{value[:300]} does not exist in the selected workspace or session.')
        return str(resolved)

    result = arguments.copy()
    for field in (*inputs, *outputs):
        if field not in arguments or field not in fields:
            continue
        value = arguments[field]
        kind = fields[field].get('type')
        if kind == 'array' and isinstance(value, list):
            result[field] = [path_value(item, field, False) for item in value]
        elif kind == 'string':
            result[field] = path_value(value, field, field in outputs)
    if name == 'capture_browser_scenario' and isinstance(arguments.get('browser'), dict):
        browser = arguments['browser']
        if browser.get('mode') == 'launch' and 'executable_path' in browser:
            result['browser'] = {**browser, 'executable_path': path_value(browser['executable_path'], 'browser.executable_path', False)}
    return result
