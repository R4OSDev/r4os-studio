"""Build the official REA source with its own pinned Node, without global setup."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

from managed_download import node_plan,install_node,file_hash
import runtime_spec

RECIPE_VERSION=1


def command(stage,work,arguments,network=False,readonly=False):
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    if not network:args+=['--unshare-net']
    for path in ('/usr','/lib','/lib64'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    args+=['--symlink','/usr/bin','/bin','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/etc',
           '--ro-bind' if readonly else '--bind',str(stage),'/runtime','--bind',str(work),'/work']
    for path in ('/etc/passwd','/etc/group','/etc/nsswitch.conf','/etc/os-release'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    if network:
        for path in ('/etc/ssl','/etc/resolv.conf','/etc/hosts'):
            if Path(path).exists():args+=['--ro-bind',path,path]
    args+=['--chdir','/runtime/Repository','--clearenv','--setenv','HOME','/work/Home',
           '--setenv','PATH','/runtime/Node/bin:/usr/bin:/bin','--setenv','LANG','C.UTF-8',
           '--setenv','HUSKY','0','--setenv','npm_config_cache','/work/Cache','--setenv','npm_config_userconfig','/dev/null',
           '--setenv','npm_config_audit','false','--setenv','npm_config_fund','false',
           '--setenv','TURBO_TELEMETRY_DISABLED','1','--setenv','DO_NOT_TRACK','1',
           '--setenv','GOMAXPROCS','2','--setenv','UV_THREADPOOL_SIZE','2',
           '--setenv','REA_MCP_INPUT_SCHEMA_PROFILE','full','--setenv','REA_MCP_OUTPUT_SCHEMA_PROFILE','full',
           '--',*arguments]
    return args


def run(api,stage,work,label,arguments,network=False,timeout=1200):
    log=work/(label+'.log')
    if log.exists():raise api.SkillFault('The original REA build phase already has a log. Reconcile its request before repeating it.',409)
    with log.open('xb') as stream:
        result=subprocess.run(command(stage,work,arguments,network),stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,
                              timeout=timeout,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        stream.flush();os.fsync(stream.fileno())
    proof=dict(phase=label,exit=result.returncode,network=network)
    api.atomic(work/(label+'-receipt.json'),(api.encode(proof)+'\n').encode())
    if result.returncode:
        raise api.SkillFault('The managed REA '+label+' phase failed. Its original private log and previous active package were preserved.',409)
    return proof


def inventory(root):
    files=[]
    for parent,folders,names in os.walk(root,followlinks=False):
        for name in folders+names:
            path=Path(parent)/name;relative=path.relative_to(root).as_posix();runtime_spec.relative(relative)
            if path.is_symlink():
                if not path.resolve(strict=True).is_relative_to(root) or Path(os.readlink(path)).is_absolute():
                    raise ValueError('A built runtime link leaves its own tree.')
                files.append(dict(path=relative,link=os.readlink(path)))
            elif path.is_file():
                files.append(dict(path=relative,sha256=file_hash(path),bytes=path.stat().st_size,executable=bool(path.stat().st_mode&0o111)))
            elif not path.is_dir():raise ValueError('The built runtime has a special entry.')
    return sorted(files,key=lambda item:item['path'])


async def probe(api,stage,work,expected,job):
    spec=importlib.util.spec_from_file_location('rea_recipe_mcp_client',Path(__file__).resolve().parents[1]/'agent-sessions/skill_mcp_client.py')
    client_api=importlib.util.module_from_spec(spec);spec.loader.exec_module(client_api)
    state=api.folder(work/'Probe',True)
    client=client_api.Client(state,dict(skillId=job['skillId'],requestId=job['requestId'],sourceCommit=job['commit']))
    try:
        value=await client.start(command(stage,work,['/runtime/Node/bin/node','/runtime/Repository/scripts/rea.mjs','mcp'],readonly=True),
                                 env={'LANG':'C.UTF-8'})
        tools=await client.discover()
        if tools!=expected['tools'] or value['serverInfo']['version']!=expected['info']['version']:
            raise api.SkillFault('The built REA MCP contracts differ from their generated catalogue.',503)
        result=dict(protocol=value['protocolVersion'],serverInfo=value['serverInfo'],tools=len(tools),exactCatalogue=True)
    finally:
        end=await client.close(grace=15)
        api.atomic(work/'probe-process-end.json',(api.encode(end)+'\n').encode())
        if not end.get('processEndConfirmed') or end.get('exit')!=0 or end.get('unresolved'):
            raise api.SkillFault('The original REA preparation probe did not confirm a clean process end.',409)
    return result


def prepare(api,skills,ident,job,source,source_manifest,progress):
    if (job['configuration']['repository']!='https://github.com/morluto/rea'
            or job['configuration']['skillPath'] not in ('.agents/skills/reverse-engineer-anything','skills/reverse-engineer-anything')):
        raise api.SkillFault('The REA recipe requires its official repository and canonical skill directory.',409)
    repository=source/'Repository'
    package=json.loads(api.regular(repository/'package.json')[0])
    if package.get('name')!='rea-agents' or not isinstance(package.get('version'),str):
        raise api.SkillFault('The selected source is not the official REA package.',409)
    # Dependency install has no lifecycle execution. Later source scripts run offline.
    npm_config=api.regular(repository/'.npmrc')[0].decode().strip()
    if npm_config!='engine-strict=true':
        raise api.SkillFault('This REA source changes npm configuration beyond the managed recipe. Review it before preparation.',409)
    lock_raw=runtime_spec.read(repository/'package-lock.json')
    lock=json.loads(lock_raw)
    for record in lock.get('packages',{}).values():
        resolved=record.get('resolved')
        if resolved is not None and (not isinstance(resolved,str) or urlsplit(resolved).scheme!='https'
                or urlsplit(resolved).netloc!='registry.npmjs.org' or not isinstance(record.get('integrity'),str)):
            raise api.SkillFault('The REA dependency lock contains an unreviewed external source.',409)
    progress(phase='preparing_node')
    node=node_plan(api,skills,repository)
    source_hash=file_hash(source/'manifest.json')
    script=Path(__file__).resolve()
    recipe_files=[script,script.with_name('managed_download.py'),script.with_name('runtime_spec.py'),script.parents[1]/'../shared/rea-skill-guide.md']
    recipe={file.name:file_hash(file.resolve()) for file in recipe_files}
    identity=dict(recipeVersion=RECIPE_VERSION,recipeFiles=recipe,sourceCommit=source_manifest['commit'],sourceManifestHash=source_hash,
                  dependencyLockHash=hashlib.sha256(lock_raw).hexdigest(),node={k:node[k] for k in ('version','sha256','architecture')})
    key=hashlib.sha256(api.encode(identity).encode()).hexdigest()
    parent=api.folder(skills/ident/'Runtimes'/source_manifest['commit'],True)
    destination=parent/key
    def existing():
        raw=runtime_spec.read(destination/'runtime.json')
        binding=dict(schema=1,repository=job['configuration']['repository'],commit=source_manifest['commit'],sourceManifestHash=source_hash,
                     skillPath=job['configuration']['skillPath'],recipe='rea',importedHash=api.inventory(destination/'Skill')[2],
                     runtime=dict(path=destination.relative_to(skills/ident).as_posix(),manifestHash=hashlib.sha256(raw).hexdigest(),version=package['version']))
        runtime_spec.load(skills,ident,binding,complete=True)
        return destination/'Skill',binding['runtime']
    if destination.exists():
        progress(phase='verifying_runtime')
        return existing()
    work=api.folder(skills/ident/'Builds'/job['requestId'],True)
    if any(work.iterdir()):raise api.SkillFault('The original REA build workspace exists. Reconcile it before another build.',409)
    for name in ('Home','Cache'):api.folder(work/name,True)
    stage=parent/('.stage-'+job['requestId']);stage.mkdir(mode=0o700)
    api.atomic(work/'build-intent.json',(api.encode(identity)+'\n').encode())
    node_runtime=install_node(api,node,stage/'Node')
    shutil.copytree(repository,stage/'Repository',symlinks=False)
    receipts=[run(api,stage,work,'node-version',['/runtime/Node/bin/node','--version'],timeout=30),
              run(api,stage,work,'npm-version',['/runtime/Node/bin/npm','--version'],timeout=30)]
    if (work/'node-version.log').read_text().strip()!=node['version']:
        raise api.SkillFault('The actual managed Node version differs from its official artifact identity.',503)
    node_runtime['npmVersion']=(work/'npm-version.log').read_text().strip()
    progress(phase='installing_dependencies')
    receipts.append(run(api,stage,work,'dependencies',['/runtime/Node/bin/npm','ci','--ignore-scripts','--no-audit','--no-fund','--registry=https://registry.npmjs.org'],network=True))
    progress(phase='building_runtime')
    receipts.append(run(api,stage,work,'prepare',['/runtime/Node/bin/npm','run','prepare']))
    receipts.append(run(api,stage,work,'build',['/runtime/Node/bin/npm','run','build:cached']))
    generated=api.folder(stage/'Repository/skills/reverse-engineer-anything')
    shutil.copytree(generated,stage/'Skill',symlinks=False)
    skill_path=stage/'Skill/SKILL.md';raw=api.regular(skill_path)[0]
    boundary=raw.find(b'\n---\n',4)
    if not raw.startswith(b'---\n') or boundary<0:raise api.SkillFault('The generated REA skill has no valid frontmatter boundary.',409)
    guide=(script.parents[1]/'../shared/rea-skill-guide.md').resolve().read_bytes()
    api.atomic(skill_path,raw[:boundary+5]+b'\n'+guide+b'\n'+raw[boundary+5:])
    files,contents,tree_hash=api.inventory(stage/'Skill')
    validation=api.validate(files,contents,tree_hash,'/usr/bin/node')
    if not validation['valid']:raise api.SkillFault('The generated complete REA skill failed validation: '+'; '.join(validation['errors']),409)
    catalog=json.loads(runtime_spec.read(stage/'Repository/dist/mcp-catalog-full.json'))
    progress(phase='probing_runtime')
    native=asyncio.run(probe(api,stage,work,catalog,dict(job,commit=source_manifest['commit'])))
    # Build caches are operational data, not part of the immutable executable set.
    for path in (stage/'Repository/.turbo',stage/'Repository/.cache'):
        if path.exists():shutil.rmtree(path)
    value=dict(schema=1,recipe='rea',version=package['version'],source=dict(repository=job['configuration']['repository'],
               commit=source_manifest['commit'],manifestHash=source_hash),node=node_runtime,
               entry=dict(path='Repository/scripts/rea.mjs',sha256=file_hash(stage/'Repository/scripts/rea.mjs'),arguments=['mcp']),
               catalog=dict(path='Repository/dist/mcp-catalog-full.json',sha256=file_hash(stage/'Repository/dist/mcp-catalog-full.json')),
               programs={},environment={},build=dict(identity=identity,receipts=receipts,probe=native,programProvisioning='separate-analysis-program-step'),
               files=inventory(stage))
    api.atomic(stage/'runtime.json',(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode('ascii'))
    runtime_spec.verify_files(stage,value['files'])
    for directory,_,names in os.walk(stage,topdown=False):
        for name in names:
            file=Path(directory)/name
            if file.is_symlink():continue
            with file.open('rb') as stream:os.fsync(stream.fileno())
        api.sync(Path(directory))
    os.rename(stage,destination);api.sync(parent)
    return existing()
