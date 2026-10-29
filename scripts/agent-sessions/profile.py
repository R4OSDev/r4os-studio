"""Qualified, unmodified Codex runtime. Never parses or copies provider credentials."""
import hashlib
import json
import os
from pathlib import Path
import resource
import stat

CODEX_VERSION = '0.163.0'
CODEX_SHA256 = '399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215'
LEGACY_PROFILE = 'studio-tools-v1'
DEVELOPMENT_PROFILE = 'studio-tools-v2'
VM_PROFILE = 'studio-tools-v3'
COMPLETION_PROFILE = 'studio-tools-v4'
UPDATE_PROFILE = 'studio-tools-v5'
GIT_PROFILE = 'studio-tools-v6'
GUI_PROFILE = 'studio-tools-v7'
ROADMAP_PROFILE = 'studio-tools-v8'
REMOTE_PROFILE = 'studio-tools-v9'
DOCUMENT_PROFILE = 'studio-tools-v10'
IMAGE_PROFILE = 'studio-tools-v11'
CONTRACT_PROFILE = 'studio-tools-v12'
NOTES_PROFILE = 'studio-tools-v13'
IMAGE_PROFILES = (IMAGE_PROFILE, CONTRACT_PROFILE, NOTES_PROFILE)
REMOTE_PROFILES = (REMOTE_PROFILE,DOCUMENT_PROFILE,*IMAGE_PROFILES)
PROFILE = NOTES_PROFILE
SKILL_PROFILE = 'studio-skill-tools-v1'
AUTHOR_PROFILE = 'studio-skill-tools-v2'
DOCUMENT_SKILL_PROFILE = 'studio-skill-tools-v3'
IMAGE_SKILL_PROFILE = 'studio-skill-tools-v4'
NOTES_SKILL_PROFILE = 'studio-skill-tools-v5'
SKILL_PROFILES = (SKILL_PROFILE, AUTHOR_PROFILE,DOCUMENT_SKILL_PROFILE,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE)
NOTE_TOOLS = ('read_environment_notes','record_environment_note')
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
ROADMAP_TOOLS = ('read_roadmap', 'update_roadmap', 'cleanup_roadmap')
PRE_ROADMAP_TOOLS = LEGACY_TOOLS + DEVELOPMENT_TOOLS + GIT_TOOLS
PRE_REMOTE_TOOLS = PRE_ROADMAP_TOOLS + ROADMAP_TOOLS
REMOTE_TOOLS = ('get_remote_host', 'run_remote_command', 'remote_files', 'read_remote_job', 'stop_remote_job')
PRE_ATTACHMENT_TOOLS = PRE_REMOTE_TOOLS + REMOTE_TOOLS
ATTACHMENT_TOOLS = ('read_attachment',)
PRE_IMAGE_TOOLS = PRE_ATTACHMENT_TOOLS + ATTACHMENT_TOOLS
IMAGE_TOOLS = ('list_generated_images','import_generated_image')
TOOLS = PRE_IMAGE_TOOLS + IMAGE_TOOLS

def tools_for(profile):
    if profile == NOTES_PROFILE:return TOOLS + NOTE_TOOLS
    if profile == NOTES_SKILL_PROFILE:return tools_for(IMAGE_SKILL_PROFILE) + NOTE_TOOLS
    if profile == SKILL_PROFILE: return LEGACY_TOOLS
    if profile == AUTHOR_PROFILE: return LEGACY_TOOLS + AUTHOR_TOOLS
    if profile == DOCUMENT_SKILL_PROFILE:return LEGACY_TOOLS+AUTHOR_TOOLS+ATTACHMENT_TOOLS
    if profile == IMAGE_SKILL_PROFILE:return LEGACY_TOOLS+AUTHOR_TOOLS+ATTACHMENT_TOOLS+('list_generated_images',)
    if profile == LEGACY_PROFILE: return LEGACY_TOOLS
    if profile == DEVELOPMENT_PROFILE: return LEGACY_TOOLS + PREVIOUS_DEVELOPMENT_TOOLS
    if profile == VM_PROFILE: return LEGACY_TOOLS + VM_TOOLS
    if profile == COMPLETION_PROFILE: return LEGACY_TOOLS + COMPLETION_TOOLS
    if profile == UPDATE_PROFILE: return LEGACY_TOOLS + DEVELOPMENT_TOOLS
    if profile in (GIT_PROFILE, GUI_PROFILE): return PRE_ROADMAP_TOOLS
    if profile == ROADMAP_PROFILE: return PRE_REMOTE_TOOLS
    if profile == REMOTE_PROFILE: return PRE_ATTACHMENT_TOOLS
    if profile == DOCUMENT_PROFILE:return PRE_IMAGE_TOOLS
    if profile in IMAGE_PROFILES:return TOOLS
    raise ValueError('This session profile needs compatible Studio host support.')


def permission_tools(profile):
    # Roadmap has one grouped setting, outside the original permission map.
    return tuple(t for t in tools_for(profile) if t not in (*ROADMAP_TOOLS,*NOTE_TOOLS))


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


def prepare(binary, provider_home, state, features, model=None, catalog_source=None, selected_profile=PROFILE, fast_mode=False, web_search_enabled=False, goals_enabled=False, attachment_mounts=(),image_modalities=None,image_generation_enabled=False,generated_root=None):
    if type(web_search_enabled) is not bool: raise ValueError('Invalid Web search setting.')
    if type(goals_enabled) is not bool: raise ValueError('Invalid native Goal capability.')
    if type(image_generation_enabled) is not bool:raise ValueError('Invalid native image generation capability.')
    if image_generation_enabled and 'image_generation' not in features:raise ValueError('This runtime has no qualified native image generation feature.')
    if goals_enabled and 'goals' not in features: raise ValueError('This runtime has no qualified Goal feature.')
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
    stale_modalities=(image_modalities is not None and catalog.exists() and model and not missing_model
        and next(v for v in json.loads(regular(catalog).read_text())['models'] if v.get('slug')==model).get('input_modalities',['text','image'])!=image_modalities)
    if not catalog.exists() or missing_model or stale_modalities or (catalog_source and previous_source and previous_source['providerId'] != catalog_source):
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
    if image_modalities is not None and (not model or next(m for m in data['models'] if m['slug']==model).get('input_modalities',['text','image'])!=image_modalities):
        raise ValueError('The selected native image modalities changed before this run. The conversation was preserved.')
    # The feature-name set is a versioned part of the qualified profile. Only
    # booleans and FeatureToml switches are included; bare config structs are not.
    settings = {
        'cli_auth_credentials_store': 'file', 'model_catalog_json': '/session/models.json',
        'sqlite_home': '/session/state', 'log_dir': '/session/logs', 'project_doc_max_bytes': 0,
        'project_root_markers': [], 'web_search': 'live' if web_search_enabled else 'disabled',
        'agents.enabled': False, 'tools.update_plan.enabled': False,
        'tools.experimental_request_user_input.enabled': False,
        'skills.include_instructions': False, 'skills.bundled.enabled': False,
        'cloud.skills.enabled': False, 'plugins._default.enabled': False,
        # Reflect the writable workspace exposed by Studio's dynamic tools.
        # Native tools stay disabled; their virtual cwd contains no project data.
        'history.persistence': 'none', 'approval_policy': 'never', 'sandbox_mode': SANDBOX_MODE,
    }
    settings.update({'features.' + name: False for name in features})
    if selected_profile in (*IMAGE_PROFILES,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE):
        from image_provider import PROVIDER
        settings['model_provider']=PROVIDER
    settings['features.fast_mode'] = fast_mode
    settings['features.sqlite'] = True
    settings['features.skip_host_skill_discovery'] = True
    # Only a qualified controller/worker opts in. Ordinary one-turn workers
    # retain the previous feature set until their lifecycle supports Goals.
    if goals_enabled: settings['features.goals'] = True
    if image_generation_enabled:
        settings['features.image_generation']=True
        if 'imagegenext' in features:settings['features.imagegenext']=True
    # Hide user config in the runtime mount namespace; the original file is
    # never rewritten. The virtual cwd is empty and contains no project config.
    (state / 'config.toml').write_text('')
    args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid']
    for path in ('/usr', '/lib', '/lib64'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    args += ['--dir', '/etc']
    for path in ('/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    if attachment_mounts:
        if len(attachment_mounts)>256:raise ValueError('Too many native attachment mounts.')
        args+=['--dir','/attachments']
        import re
        seen=set()
        for source,target in attachment_mounts:
            if not re.fullmatch(r'/attachments/[a-f0-9-]{36}\.(png|jpg|webp)',target) or target in seen:raise ValueError('Invalid native image target.')
            seen.add(target);args+=['--ro-bind',str(regular(source)),target]
    if image_generation_enabled:
        if selected_profile not in (*IMAGE_PROFILES,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE) or generated_root is None:raise ValueError('Native image generation requires its qualified session output mount.')
        generated_root=directory(generated_root)
        directory(provider_home/'generated_images')
    # A native conversation grows across many turns and includes image inputs.
    # Exempt only Codex from the worker's soft per-file limit. Older hosts keep
    # their inherited hard bound until explicit history-support maintenance.
    hard_limit = resource.getrlimit(resource.RLIMIT_FSIZE)[1]
    native_limit = 'unlimited' if hard_limit == resource.RLIM_INFINITY else str(hard_limit)
    args += ['--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
             '--bind', str(provider_home), '/codex', '--bind', str(state), '/session',
             '--bind', str(state / 'native'), '/codex/sessions',
             '--bind', str(state / 'archived'), '/codex/archived_sessions',
             '--ro-bind', str(state / 'config.toml'), '/codex/config.toml',
             '--dir', '/workspace', '--dir', '/bin', '--ro-bind', str(binary), '/bin/codex',
             '--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/session/home',
             '--setenv', 'CODEX_HOME', '/codex', '--setenv', 'PATH', '/usr/bin:/bin',
             '--setenv', 'LANG', 'C.UTF-8', '/usr/bin/prlimit',
             '--fsize=' + native_limit + ':' + native_limit, '--', '/bin/codex', 'app-server', '--listen', 'stdio://']
    if generated_root is not None:
        if not image_generation_enabled:raise ValueError('An output mount requires enabled native image generation.')
        position=args.index('--chdir');args[position:position]=['--bind',str(generated_root),'/codex/generated_images']
    for key, value in settings.items():
        args += ['-c', key + '=' + json.dumps(value, ensure_ascii=False, separators=(',', ':'))]
    if selected_profile in (*IMAGE_PROFILES,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE):
        from image_provider import configuration
        args+=['-c',configuration()]
    return args, {'profile': selected_profile, 'version': CODEX_VERSION, 'sha256': CODEX_SHA256,
                  'catalogSha256': digest(catalog)}
