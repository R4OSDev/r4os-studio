"""Frozen source/runtime references and a separate credential-free namespace."""
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import json
from owner import skills_root
from skill_mcp_client import Client, McpFault, directory, encoded,atomic

spec = importlib.util.spec_from_file_location('managed_skill_runtime_spec', Path(__file__).resolve().parents[1] / 'skills/runtime_spec.py')
runtime_spec = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime_spec)


def freeze(projects, ident, source):
    try:
        root, manifest, catalog = runtime_spec.load(skills_root(projects), ident, source)
        return dict(schema=1, sourceBinding=source, catalogHash=manifest['catalog']['sha256'],
                    toolsHash=hashlib.sha256(encoded(catalog['tools'])).hexdigest(), tools=len(catalog['tools']))
    except (OSError, ValueError, KeyError, TypeError):
        from store import ProjectFault
        raise ProjectFault('The managed skill runtime is incomplete or changed. Review its original preparation before running.', 409) from None


def load(worker, entry, complete=False):
    frozen = entry.get('mcp')
    if not isinstance(frozen, dict) or frozen.get('schema') != 1: raise McpFault('This accepted run has no managed runtime for the selected skill.')
    root, manifest, catalog = runtime_spec.load(skills_root(worker.store.projects), entry['id'], frozen['sourceBinding'], complete=complete)
    if (manifest['catalog']['sha256'] != frozen['catalogHash']
            or hashlib.sha256(encoded(catalog['tools'])).hexdigest() != frozen['toolsHash']
            or len(catalog['tools']) != frozen['tools']): raise McpFault('The frozen MCP catalogue changed.')
    return root, manifest, catalog


def namespace(worker, root, manifest, state,egress=None):
    permissions = worker.config['permissions']
    if not permissions.get('studio.exec_command') or not permissions.get('studio.read_file'):
        raise McpFault('Managed analysis requires Run command and Read file permissions for this run.')
    args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-user', '--uid', '0', '--gid', '0',
            '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts', '--hostname', 'studio-skill',
            '--cap-add', 'CAP_NET_ADMIN', '--cap-add', 'CAP_SETPCAP']
    for path in ('/usr', '/lib', '/lib64'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    args += ['--symlink', '/usr/bin', '/bin', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/etc',
             '--dir','/runner','--ro-bind',str(Path(__file__).with_name('skill_namespace_entry.py')),'/runner/skill_namespace_entry.py',
             '--ro-bind',str(Path(__file__).with_name('skill_chromium.sh')),'/runner/chromium',
             '--ro-bind',str(Path(__file__).resolve().parents[2]/'shared/skill-hosts'),'/etc/hosts',
             '--ro-bind', str(root), '/runtime', '--bind', str(state / 'Data'), '/session',
             '--bind' if permissions.get('studio.write_file') else '--ro-bind', str(worker.store.workspace), '/workspace']
    for path in ('/etc/passwd', '/etc/group', '/etc/nsswitch.conf', '/etc/os-release'):
        if Path(path).exists(): args += ['--ro-bind', path, path]
    from attachment_files import mounts
    originals = mounts(worker) if permissions.get('studio.read_attachment') else []
    if originals:
        args += ['--dir', '/attachments']
        for source, target in originals: args += ['--ro-bind', source, target]
    for name in ('Home','Cache','Evidence'):
        directory(state / 'Data' / name)
    args += ['--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/session/Home',
             '--setenv', 'XDG_CACHE_HOME', '/session/Cache', '--setenv', 'LANG', 'C.UTF-8',
             '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--setenv', 'PYTHONNOUSERSITE', '1',
             '--setenv', 'PATH', '/runtime/Programs/Bin:/runtime/Programs/Java/bin:/runtime/Programs/Python/bin:/runtime/Programs/OsTools/usr/bin:/runtime/Programs/OsTools/usr/sbin:/runtime/Programs/Wabt/bin:/runtime/' + str(Path(manifest['node']['path']).parent) + ':/usr/bin:/bin',
             '--setenv', 'REA_BUILD_COMMIT', manifest['source']['commit'],
             '--setenv', 'REA_MCP_INPUT_SCHEMA_PROFILE', 'full', '--setenv', 'REA_MCP_OUTPUT_SCHEMA_PROFILE', 'full']
    environment_names=('GHIDRA_INSTALL_DIR','JAVA_HOME','REA_JADX_MCP_JAR','REA_WABT_BIN_DIRECTORY',
        'REA_SIGROK_COMMAND','REA_PWNTOOLS_PYTHON','REA_MITMDUMP_COMMAND','REA_BROWSER_EXECUTABLE',
        'SIGROKDECODE_DIR','REA_WAKARU_COMMAND','REA_PWNDBG_GDB','REA_PWNDBG_GDBINIT','REA_PWNDBG_VENV_PATH','WIRESHARK_DATA_DIR',
        'PLAYWRIGHT_BROWSERS_PATH','LD_LIBRARY_PATH','REA_UNBLOB_COMMAND','REA_BINWALK_COMMAND')
    for name, value in manifest.get('environment', {}).items():
        if name=='REA_BROWSER_NO_SANDBOX' and value=='true':
            # Chromium remains inside the already sealed OS namespace.
            args += ['--setenv',name,value];continue
        if name not in environment_names or not isinstance(value,str) or not all(
                part.startswith('/runtime/') and '..' not in Path(part).parts for part in value.split(':')):
            raise McpFault('A runtime recipe attempted to provide an unrecognised environment value.')
        args += ['--setenv', name, value]
    browser=manifest.get('environment',{}).get('REA_BROWSER_EXECUTABLE')
    browser_environment=dict(PATH='/runtime/Programs/Bin:/runtime/Programs/Java/bin:/runtime/Programs/Python/bin:/runtime/Programs/OsTools/usr/bin:/usr/bin:/bin',
        HOME='/session/Home',XDG_CACHE_HOME='/session/Cache',LANG='C.UTF-8')
    if manifest.get('environment',{}).get('LD_LIBRARY_PATH'):
        browser_environment['LD_LIBRARY_PATH']=manifest['environment']['LD_LIBRARY_PATH']
    if browser:
        args+=['--setenv','REA_BROWSER_EXECUTABLE','/runner/chromium']
    if permissions.get('studio.skill_network'):
        if egress is None:raise McpFault('This run has no prepared private skill web proxy.')
        args+=['--ro-bind',str(egress),'/runner/egress.sock','--ro-bind',str(Path(__file__).with_name('skill_net_bridge.py')),'/runner/skill_net_bridge.py']
        if Path('/etc/ssl/certs').exists():args+=['--dir','/etc/ssl','--ro-bind','/etc/ssl/certs','/etc/ssl/certs']
        proxy_environment=dict(HTTP_PROXY='http://127.0.0.1:3128',HTTPS_PROXY='http://127.0.0.1:3128',
                http_proxy='http://127.0.0.1:3128',https_proxy='http://127.0.0.1:3128',
                NO_PROXY='localhost,127.0.0.1,::1,studio-skill',no_proxy='localhost,127.0.0.1,::1,studio-skill',
                NODE_USE_ENV_PROXY='1',STUDIO_SKILL_PROXY='http://127.0.0.1:3128')
        for name,value in proxy_environment.items():args+=['--setenv',name,value]
        browser_environment.update(proxy_environment)
    if browser:
        control=directory(state/'Control');configuration=control/'Browser.json'
        atomic(configuration,encoded(dict(schema=1,executable=browser,environment=browser_environment,
            proxy='http://127.0.0.1:3128' if permissions.get('studio.skill_network') else None)))
        args+=['--ro-bind',str(configuration),'/runner/browser.json',
            '--ro-bind',str(Path(__file__).with_name('skill_browser_launch.py')),'/runner/skill_browser_launch.py']
    args += ['--','/usr/bin/python3','-I','-B','/runner/skill_namespace_entry.py',
             '/runtime/' + manifest['node']['path'], '/runtime/' + manifest['entry']['path'], *manifest['entry']['arguments']]
    return args


async def local_start(worker, entry, progress=None):
    root, manifest, _ = await asyncio.to_thread(load, worker, entry, True)
    state = directory(worker.store.directory / worker.session_id / 'SkillMCP' / entry['id'] / worker.run_id)
    directory(state / 'Data')
    binding = dict(ownerType=worker.store.owner_type, ownerId=worker.store.owner_id, sessionId=worker.session_id,
                   runId=worker.run_id, skillId=entry['id'], packageHash=entry['activeHash'],
                   runtimeManifestHash=entry['mcp']['sourceBinding']['runtime']['manifestHash'])
    client = Client(state / 'Transport', binding, progress)
    try:
        await client.start(namespace(worker, root, manifest, state), env={'LANG':'C.UTF-8'})
        tools = await client.discover()
        if hashlib.sha256(encoded(tools)).hexdigest() != entry['mcp']['toolsHash']:
            raise McpFault('The actual server tool contracts differ from this run\'s immutable catalogue.')
        return client
    except BaseException:
        await client.close()
        raise


async def start(worker,entry):
    from skill_session_client import start as session_start
    return await session_start(worker,entry)
