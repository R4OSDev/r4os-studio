"""Qualified, unmodified Codex runtime. Never parses or copies provider credentials."""
import hashlib
import json
import os
from pathlib import Path
import stat

CODEX_VERSION = '0.163.0'
CODEX_SHA256 = '399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215'
LEGACY_PROFILE = 'studio-tools-v1'
DEVELOPMENT_PROFILE = 'studio-tools-v2'
VM_PROFILE = 'studio-tools-v3'
COMPLETION_PROFILE = 'studio-tools-v4'
UPDATE_PROFILE = 'studio-tools-v5'
PROFILE = 'studio-tools-v6'
SKILL_PROFILE = 'studio-skill-tools-v1'
AUTHOR_PROFILE = 'studio-skill-tools-v2'
SKILL_PROFILES = (SKILL_PROFILE, AUTHOR_PROFILE)
AUTHOR_TOOLS = ('validate_skill', 'save_skill')
SANDBOX_MODE = 'workspace-write'
LEGACY_TOOLS = ('exec_command', 'write_stdin', 'terminate_process', 'list_directory', 'read_file',
         'search', 'write_file', 'apply_patch', 'create_directory')
PREVIOUS_DEVELOPMENT_TOOLS = ('build_project', 'deploy_project', 'run_project', 'read_development_job',
    'stop_development_job', 'capture_vm', 'send_vm_input')
VM_TOOLS = PREVIOUS_DEVELOPMENT_TOOLS + ('start_project_vm',)
COMPLETION_TOOLS = VM_TOOLS + ('complete_development_job',)
UPDATE_TOOLS = ('read_update_package', 'plan_update_package', 'build_update_package', 'check_update_vm',
    'upload_update_package', 'install_update_package', 'commit_update', 'verify_update', 'resume_update',
    'abort_update', 'rollback_update', 'cleanup_update_transport')
DEVELOPMENT_TOOLS = COMPLETION_TOOLS + UPDATE_TOOLS
GIT_TOOLS = ('push_project',)
def default_enabled(tool): return tool not in ('commit_update','rollback_update','push_project')
TOOLS = LEGACY_TOOLS + DEVELOPMENT_TOOLS + GIT_TOOLS

def tools_for(profile):
    if profile == SKILL_PROFILE: return LEGACY_TOOLS
    if profile == AUTHOR_PROFILE: return LEGACY_TOOLS + AUTHOR_TOOLS
    if profile == LEGACY_PROFILE: return LEGACY_TOOLS
    if profile == DEVELOPMENT_PROFILE: return LEGACY_TOOLS + PREVIOUS_DEVELOPMENT_TOOLS
    if profile == VM_PROFILE: return LEGACY_TOOLS + VM_TOOLS
    if profile == COMPLETION_PROFILE: return LEGACY_TOOLS + COMPLETION_TOOLS
    if profile == UPDATE_PROFILE: return LEGACY_TOOLS + DEVELOPMENT_TOOLS
    if profile == PROFILE: return TOOLS
    raise ValueError('This session profile needs compatible Studio host support.')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def regular(path):
    p = Path(path).absolute()
    if p.resolve(strict=True) != p or not stat.S_ISREG(p.lstat().st_mode):
        raise ValueError('Invalid agent runtime file.')
    return p


def directory(path):
    p = Path(path).absolute()
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    if p.resolve(strict=True) != p or not stat.S_ISDIR(p.lstat().st_mode):
        raise ValueError('Invalid agent runtime directory.')
    return p


def write_json(path, value):
    p = Path(path)
    tmp = p.with_name(p.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)
    fd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def prepare(binary, provider_home, state, features, model=None, catalog_source=None, selected_profile=PROFILE, fast_mode=False):
    tools_for(selected_profile)
    binary = regular(binary)
    if digest(binary) != CODEX_SHA256:
        raise ValueError('This Codex version has not been qualified for agent runs.')
    provider_home = directory(provider_home)
    state = directory(state)
    # These are empty mount targets in the existing provider home. All native
    # conversation writes are redirected into the project's own state directory.
    for name in ('sessions', 'archived_sessions'):
        directory(provider_home / name)
    mount_config = provider_home / 'config.toml'
    if not mount_config.exists():
        fd = os.open(mount_config, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    regular(mount_config)
    for name in ('native', 'archived', 'state', 'logs', 'home'):
        directory(state / name)
    catalog = state / 'models.json'
    source = state / 'models.provider.json'
    previous_source = json.loads(regular(source).read_text()) if source.exists() else None
    missing_model = catalog.exists() and model and not any(v.get('slug') == model for v in json.loads(regular(catalog).read_text())['models'])
    if not catalog.exists() or missing_model or (catalog_source and previous_source and previous_source['providerId'] != catalog_source):
        # Only non-secret model metadata is read. AuthManager continues to use
        # the one original credential store and its original physical locks.
        cache = json.loads(regular(provider_home / 'models_cache.json').read_text())
        models = cache.get('models')
        if not isinstance(models, list) or not models:
            raise ValueError('Refresh this provider model catalog before starting a session.')
        for value in models:
            value.update(shell_type='disabled', apply_patch_tool_type=None,
                         experimental_supported_tools=[], tool_mode='direct', multi_agent_version=None,
                         supports_search_tool=False, include_skills_usage_instructions=False,
                         include_plugin_usage_instructions=False, include_apps_usage_instructions=False)
        write_json(catalog, {'models': models})
    if catalog_source: write_json(source, {'providerId': catalog_source})
    data = json.loads(regular(catalog).read_text())
    for value in data['models']:
        if (value.get('shell_type') != 'disabled' or value.get('apply_patch_tool_type') is not None
            or value.get('experimental_supported_tools') or value.get('tool_mode') != 'direct'
            or value.get('multi_agent_version') is not None or value.get('supports_search_tool')):
            raise ValueError('The agent model tool profile changed.')
    if model and not any(m['slug'] == model for m in data['models']):
        raise ValueError('The selected model is unavailable in this session profile.')
    # The feature-name set is a versioned part of the qualified profile. Only
    # booleans and FeatureToml switches are included; bare config structs are not.
    settings = {
        'cli_auth_credentials_store': 'file', 'model_catalog_json': '/session/models.json',
        'sqlite_home': '/session/state', 'log_dir': '/session/logs', 'project_doc_max_bytes': 0,
        'project_root_markers': [], 'web_search': 'disabled',
        'agents.enabled': False, 'tools.update_plan.enabled': False,
        'tools.experimental_request_user_input.enabled': False,
        'skills.include_instructions': False, 'skills.bundled.enabled': False,
        'cloud.skills.enabled': False, 'plugins._default.enabled': False,
        # Reflect the writable workspace exposed by Studio's dynamic tools.
        # Native tools stay disabled; their virtual cwd contains no project data.
        'history.persistence': 'none', 'approval_policy': 'never', 'sandbox_mode': SANDBOX_MODE,
    }
    settings.update({'features.' + name: False for name in features})
    settings['features.fast_mode'] = fast_mode
    settings['features.sqlite'] = True
    settings['features.skip_host_skill_discovery'] = True
    # Hide user config in the runtime mount namespace; the original file is
    # never rewritten. The virtual cwd is empty and contains no project config.
    (state / 'config.toml').write_text('')
    args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid']
    for path in ('/usr', '/lib', '/lib64'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    args += ['--dir', '/etc']
    for path in ('/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    args += ['--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
             '--bind', str(provider_home), '/codex', '--bind', str(state), '/session',
             '--bind', str(state / 'native'), '/codex/sessions',
             '--bind', str(state / 'archived'), '/codex/archived_sessions',
             '--ro-bind', str(state / 'config.toml'), '/codex/config.toml',
             '--dir', '/workspace', '--dir', '/bin', '--ro-bind', str(binary), '/bin/codex',
             '--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/session/home',
             '--setenv', 'CODEX_HOME', '/codex', '--setenv', 'PATH', '/usr/bin:/bin',
             '--setenv', 'LANG', 'C.UTF-8', '/bin/codex', 'app-server', '--listen', 'stdio://']
    for key, value in settings.items():
        args += ['-c', key + '=' + json.dumps(value, ensure_ascii=False, separators=(',', ':'))]
    return args, {'profile': selected_profile, 'version': CODEX_VERSION, 'sha256': CODEX_SHA256,
                  'catalogSha256': digest(catalog)}
