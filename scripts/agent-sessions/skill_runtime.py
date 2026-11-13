"""Frozen source/runtime references and a direct host execution context."""
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from workspace_context import Workspace
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


def load(worker, entry, complete=False, catalog_only=False):
    frozen = entry.get('mcp')
    if not isinstance(frozen, dict) or frozen.get('schema') != 1: raise McpFault('This accepted run has no managed runtime for the selected skill.')
    skills = skills_root(worker.store.projects)
    verify = None
    if complete:
        from functools import partial
        from rea_verification import verify as verify_runtime
        verify = partial(verify_runtime, skills/'.rea-verification', runtime_spec,
                         frozen['sourceBinding']['runtime']['manifestHash'])
    root, manifest, catalog = runtime_spec.load(skills, entry['id'], frozen['sourceBinding'],
                                               complete=complete, catalog_only=catalog_only, verify=verify)
    if (manifest['catalog']['sha256'] != frozen['catalogHash']
            or hashlib.sha256(encoded(catalog['tools'])).hexdigest() != frozen['toolsHash']
            or len(catalog['tools']) != frozen['tools']): raise McpFault('The frozen MCP catalogue changed.')
    return root, manifest, catalog


def command(worker, root, manifest, state):
    for name in ('Home', 'Cache', 'Evidence'): directory(state / 'Data' / name)
    working = Workspace(worker.store.workspace, {'/runtime': root, '/session': state / 'Data'})
    mapped = lambda value: ':'.join(str(working.path(part)) if part.startswith('/') else part for part in str(value).split(':'))
    environment = {'HOME': state / 'Data/Home', 'XDG_CACHE_HOME': state / 'Data/Cache',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
        'PYTHONPYCACHEPREFIX': state / 'Data/Cache/Python',
        'PATH': mapped('/runtime/Programs/Bin:/runtime/Programs/Java/bin:/runtime/Programs/Python/bin:/runtime/Programs/OsTools/usr/bin:/runtime/Programs/OsTools/usr/sbin:/runtime/Programs/Wabt/bin:/runtime/' + str(Path(manifest['node']['path']).parent) + ':/usr/bin:/bin'),
        'REA_BUILD_COMMIT': manifest['source']['commit'], 'REA_MCP_INPUT_SCHEMA_PROFILE': 'full',
        'REA_MCP_OUTPUT_SCHEMA_PROFILE': 'full'}
    environment.update({name: mapped(value) for name, value in manifest.get('environment', {}).items()})
    from runtime_paths import launchers
    replacements, bins = launchers(root, state / 'Data/Commands', disable_python_bytecode=True)
    for name, value in tuple(environment.items()):
        if name != 'PATH': environment[name] = replacements.get(str(value), value)
    environment['PATH'] = ':'.join([*bins, environment['PATH']])
    # Root Chromium needs its own no-sandbox switch. Studio does not create a
    # user namespace, private network, proxy, capability drop or filesystem jail.
    if environment.get('REA_BROWSER_EXECUTABLE'): environment['REA_BROWSER_NO_SANDBOX'] = 'true'
    return working.command([str(root / manifest['node']['path']), str(root / manifest['entry']['path']),
                            *manifest['entry']['arguments']], environment=environment)


async def local_start(worker, entry, progress=None):
    root, manifest, _ = await asyncio.to_thread(load, worker, entry, True)
    state = directory(worker.store.directory / worker.session_id / 'SkillMCP' / entry['id'] / worker.run_id)
    directory(state / 'Data')
    binding = dict(ownerType=worker.store.owner_type, ownerId=worker.store.owner_id, sessionId=worker.session_id,
                   runId=worker.run_id, skillId=entry['id'], packageHash=entry['activeHash'],
                   runtimeManifestHash=entry['mcp']['sourceBinding']['runtime']['manifestHash'])
    client = Client(state / 'Transport', binding, progress)
    try:
        await client.start(command(worker, root, manifest, state), env={'LANG':'C.UTF-8'})
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
