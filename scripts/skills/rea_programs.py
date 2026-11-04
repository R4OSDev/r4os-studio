"""Private, receipt-backed Linux prerequisites; never modifies the host package DB."""
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import tarfile
import zipfile

from managed_download import download, file_hash

PLAN = Path(__file__).resolve().parents[2] / 'shared/rea-programs.json'
GITHUB_HOSTS = ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com')


def unpack(archive, destination, kind, strip=True):
    destination.mkdir(mode=0o700)
    if kind == 'zip':
        with zipfile.ZipFile(archive) as stream:
            entries = stream.infolist()
            if len(entries)>100000 or sum(x.file_size for x in entries)>4*1024**3:
                raise ValueError('The managed program archive exceeds its extraction limits.')
            for item in entries:
                path=PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(item.external_attr>>16):
                    raise ValueError('The managed program zip contains a linked or escaping entry.')
                target=destination.joinpath(*path.parts)
                if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with stream.open(item) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
                target.chmod(0o755 if item.external_attr>>16&0o111 else 0o644)
    else:
        with tarfile.open(archive) as stream:
            entries=stream.getmembers()
            if len(entries)>100000 or sum(x.size for x in entries)>4*1024**3:
                raise ValueError('The managed program archive exceeds its extraction limits.')
            for item in entries:
                path=PurePosixPath(item.name)
                if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
                    raise ValueError('The managed program archive contains an unsupported entry.')
            stream.extractall(destination,filter='data')
    if strip:
        roots=list(destination.iterdir())
        if len(roots)==1 and roots[0].is_dir() and not roots[0].is_symlink():
            inner=roots[0];temporary=destination.with_name(destination.name+'-root')
            os.rename(inner,temporary);destination.rmdir();os.rename(temporary,destination)
    # Immutable runtimes have no hardlinks, privileged files or absolute links.
    for parent,folders,names in os.walk(destination,followlinks=False):
        for name in folders+names:
            target=Path(parent)/name
            if target.is_symlink():
                if Path(os.readlink(target)).is_absolute() or not target.resolve(strict=True).is_relative_to(destination):
                    raise ValueError('A managed program link leaves its installation.')
            elif target.is_file():
                if target.stat().st_nlink>1:
                    temporary=target.with_name(target.name+'.copy');shutil.copyfile(target,temporary);temporary.chmod(target.stat().st_mode&0o777);os.replace(temporary,target)
                target.chmod(0o755 if target.stat().st_mode&0o111 else 0o644)


def wrapper(bin_dir,name,text):
    target=bin_dir/name
    target.write_text('#!/bin/sh\nset -eu\n'+text+'\n');target.chmod(0o755)


def private_apt(api,stage,work,run,packages):
    apt=api.folder(work/'Apt',True)
    for name in ('lists/partial','archives/partial','log'):api.folder(apt/name,True)
    (apt/'status').write_text('')
    (apt/'sources.list').write_text('deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main\n'
        'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian-security trixie-security main\n')
    # No host config snippets, hooks, status, caches or package installation.
    options=['-o','Dir::Etc::main=/dev/null','-o','Dir::Etc::parts=-','-o','Dir::Etc::sourceparts=-',
             '-o','Dir::Etc::sourcelist=/work/Apt/sources.list','-o','Dir::State::status=/work/Apt/status',
             '-o','Dir::State::lists=/work/Apt/lists','-o','Dir::Cache::archives=/work/Apt/archives',
             '-o','Dir::Log=/work/Apt/log','-o','APT::Sandbox::User='+str(os.getuid()),'-o','APT::Get::List-Cleanup=false']
    run(api,stage,work,'program-apt-index',['/usr/bin/apt-get',*options,'update'],network=True,timeout=600)
    run(api,stage,work,'program-apt-download',['/usr/bin/apt-get',*options,'--download-only','--no-install-recommends','--yes','install',*packages],network=True,timeout=1200)
    root=api.folder(stage/'Programs/OsTools',True);receipts=[]
    for index,archive in enumerate(sorted((apt/'archives').glob('*.deb'))):
        # apt authenticated the repository Release/Packages chain and archive hashes.
        run(api,stage,work,'program-deb-'+str(index),['/usr/bin/dpkg-deb','--extract','/work/Apt/archives/'+archive.name,'/runtime/Programs/OsTools'],timeout=120)
        receipts.append(dict(archive=archive.name,sha256=file_hash(archive),bytes=archive.stat().st_size))
    links=[]
    for parent,folders,names in os.walk(root,followlinks=False):
        for name in folders+names:
            path=Path(parent)/name
            if path.is_symlink() and Path(os.readlink(path)).is_absolute():
                target=root/str(os.readlink(path)).lstrip('/');original=os.readlink(path)
                path.unlink()
                if target.exists():path.symlink_to(os.path.relpath(target,path.parent))
                else:links.append(dict(path=str(path.relative_to(root)),omittedLink=original,reason='unconfigured package alternative; maintainer scripts are not executed'))
            elif path.is_file() and not path.is_symlink():path.chmod(0o755 if path.stat().st_mode&0o111 else 0o644)
    for parent,folders,names in os.walk(root,followlinks=False):
        for name in folders+names:
            path=Path(parent)/name
            if path.is_symlink():
                try:resolved=path.resolve(strict=True)
                except (FileNotFoundError,RuntimeError):
                    links.append(dict(path=str(path.relative_to(root)),omittedLink=os.readlink(path),reason='unconfigured package alternative'))
                    path.unlink();continue
                if not resolved.is_relative_to(root):raise ValueError('A private OS package link leaves its installation.')
            elif path.is_file() and path.stat().st_nlink>1:
                temporary=path.with_name(path.name+'.private-copy');shutil.copyfile(path,temporary)
                temporary.chmod(path.stat().st_mode&0o777);os.replace(temporary,path)
    # Direct package entry points do not rely on update-alternatives.
    for name,target in [('objdump','x86_64-linux-gnu-objdump'),('readelf','x86_64-linux-gnu-readelf'),('nm','x86_64-linux-gnu-nm'),('strings','x86_64-linux-gnu-strings')]:
        path=root/'usr/bin'/name
        if not path.exists() and (path.parent/target).exists():
            if path.is_symlink():path.unlink()
            path.symlink_to(target)
    api.atomic(work/'program-debian-artifacts.json',(api.encode(dict(packages=receipts,omittedAlternatives=links,maintainerScriptsExecuted=False))+'\n').encode())
    return receipts


def configuration(stage):
    browsers=[path for pattern in ('chromium_headless_shell-*/*/headless_shell','chromium_headless_shell-*/*/chrome-headless-shell')
              for path in (stage/'Programs/Browsers').glob(pattern)]
    if len(browsers)!=1:raise ValueError('The managed browser installer did not publish one exact Chromium headless executable.')
    return {
        'GHIDRA_INSTALL_DIR':'/runtime/Programs/Ghidra','JAVA_HOME':'/runtime/Programs/Java',
        'PLAYWRIGHT_BROWSERS_PATH':'/runtime/Programs/Browsers',
        'LD_LIBRARY_PATH':'/runtime/Programs/OsTools/usr/lib/x86_64-linux-gnu:/runtime/Programs/OsTools/lib/x86_64-linux-gnu:/runtime/Programs/OsTools/usr/lib/x86_64-linux-gnu/android',
        'REA_UNBLOB_COMMAND':'/runtime/Programs/Python/bin/unblob',
        'REA_WAKARU_COMMAND':'/runtime/Programs/Wakaru/wakaru',
        'SIGROKDECODE_DIR':'/runtime/Programs/OsTools/usr/share/libsigrokdecode/decoders',
        'REA_BINWALK_COMMAND':'/runtime/Programs/Bin/binwalk',
        'REA_JADX_MCP_JAR':'/runtime/Programs/Jadxmcp/program.jar',
        'REA_WABT_BIN_DIRECTORY':'/runtime/Programs/Wabt/bin',
        'REA_SIGROK_COMMAND':'/runtime/Programs/OsTools/usr/bin/sigrok-cli',
        'REA_PWNTOOLS_PYTHON':'/runtime/Programs/Python/bin/python',
        'REA_MITMDUMP_COMMAND':'/runtime/Programs/Python/bin/mitmdump',
        'REA_BROWSER_EXECUTABLE':'/runtime/'+str(browsers[0].relative_to(stage)),
        'REA_BROWSER_NO_SANDBOX':'true',
        'REA_PWNDBG_GDB':'/runtime/Programs/OsTools/usr/bin/gdb',
        'REA_PWNDBG_GDBINIT':'/runtime/Programs/Pwndbg/lib/python3.13/site-packages/pwndbginit/gdbinit.py',
        'REA_PWNDBG_VENV_PATH':'/runtime/Programs/Pwndbg',
        'WIRESHARK_DATA_DIR':'/runtime/Programs/OsTools/usr/share/wireshark',
    }


def prepare(api,skills,stage,work,run,progress):
    plan=json.loads(PLAN.read_bytes())
    if platform.machine()!='x86_64' or platform.system()!='Linux':
        raise api.SkillFault('The complete managed analysis-program recipe currently requires Linux x86-64.',409)
    programs=api.folder(stage/'Programs',True);bins=api.folder(programs/'Bin',True);origins=[]
    for asset in plan['assets']:
        progress(phase='installing_program_'+asset['id'])
        archive=download(api,asset['url'],skills/'.downloads/programs'/asset['sha256'],asset['bytes'],asset['sha256'],GITHUB_HOSTS)
        target=programs/asset['id'].capitalize()
        if asset['format']=='jar':
            target.mkdir(mode=0o700);shutil.copyfile(archive,target/'program.jar')
        else:unpack(archive,target,asset['format'],asset['id']!='jadx')
        origins.append(asset)
    wrapper(bins,'apktool','exec /runtime/Programs/Java/bin/java -jar /runtime/Programs/Apktool/program.jar "$@"')
    wrapper(bins,'jadx','exec /runtime/Programs/Jadx/bin/jadx "$@"')
    wrapper(bins,'rizin','exec /runtime/Programs/Rizin/bin/rizin "$@"')
    frida=json.loads((stage/'Repository/node_modules/frida/package.json').read_bytes())
    expected=next(x['version'] for x in plan['assets'] if x['id']=='frida')
    if frida['version']!=expected:raise api.SkillFault('This REA dependency lock requires a different native Frida binding; review its matching official artifact before preparation.',409)
    bindings=list((programs/'Frida').rglob('frida_binding.node'))
    if len(bindings)!=1:raise api.SkillFault('The official native Frida artifact has an unexpected layout.',409)
    shutil.copyfile(bindings[0],stage/'Repository/node_modules/frida/build/frida_binding.node')
    run(api,stage,work,'program-frida-native',['/runtime/Node/bin/node','--input-type=module','-e',
        "const f=await import('/runtime/Repository/node_modules/frida/build/src/frida.js');if(typeof f.getLocalDevice!=='function')throw Error('Missing native Frida API');console.log(JSON.stringify({frida:f.version,napi:process.versions.napi,nativeBindingLoaded:true}));"],timeout=60)
    progress(phase='installing_linux_programs')
    debian=private_apt(api,stage,work,run,plan['osPackages'])
    # Build the pinned, unmodified Binwalk source offline after locked cargo fetch.
    cargo='/runtime/Programs/OsTools/usr/bin/cargo'
    run(api,stage,work,'program-binwalk-fetch',[cargo,'fetch','--locked','--manifest-path','/runtime/Repository/third_party/binwalk/Cargo.toml'],network=True)
    run(api,stage,work,'program-binwalk-build',[cargo,'build','--release','--locked','--offline','--jobs','2','--manifest-path','/runtime/Repository/third_party/binwalk/Cargo.toml'],timeout=1800)
    shutil.copyfile(stage/'Repository/third_party/binwalk/target/release/binwalk',bins/'binwalk');(bins/'binwalk').chmod(0o755)
    shutil.rmtree(stage/'Repository/third_party/binwalk/target')
    progress(phase='installing_python_programs')
    run(api,stage,work,'program-python-venv',['/usr/bin/python3','-m','venv','--copies','--without-pip','/runtime/Programs/Python'])
    uv=['/runtime/Programs/Uv/uv','pip','install','--python','/runtime/Programs/Python/bin/python','--link-mode','copy','--only-binary',':all:']
    run(api,stage,work,'program-python-build-tools',[*uv,'setuptools','wheel','build'],network=True)
    # frida-tools publishes only an sdist. Obtain its hash via PyPI, then build
    # offline: no package build hook receives the host network or credentials.
    metadata=download(api,'https://pypi.org/pypi/frida-tools/14.11.0/json',skills/'.downloads/python/frida-tools-14.11.0.json',2*1024**2)
    distribution=next(x for x in json.loads(metadata.read_bytes())['urls'] if x['packagetype']=='sdist')
    archive=download(api,distribution['url'],skills/'.downloads/python'/distribution['digests']['sha256'],distribution['size'],distribution['digests']['sha256'],('files.pythonhosted.org',))
    unpack(archive,work/'FridaTools','tar.gz');api.folder(work/'Wheels',True)
    run(api,stage,work,'program-frida-tools-build',['/runtime/Programs/Python/bin/python','-m','build','--wheel','--no-isolation','--outdir','/work/Wheels','/work/FridaTools'])
    run(api,stage,work,'program-python-wheels',[*uv,'--find-links','/work/Wheels',*plan['pythonPackages']],network=True)
    run(api,stage,work,'program-python-versions',['/runtime/Programs/Uv/uv','pip','freeze','--python','/runtime/Programs/Python/bin/python'],timeout=60)
    progress(phase='installing_browser')
    run(api,stage,work,'program-chromium',['/runtime/Node/bin/node','node_modules/playwright-core/cli.js','install','chromium','--only-shell'],network=True)
    run(api,stage,work,'program-java-version',['/runtime/Programs/Java/bin/java','-version'],timeout=30)
    run(api,stage,work,'program-javac-version',['/runtime/Programs/Java/bin/javac','-version'],timeout=30)
    run(api,stage,work,'program-ghidra-decompiler',['/usr/bin/test','-x','/runtime/Programs/Ghidra/Ghidra/Features/Decompiler/os/linux_x86_64/decompile'],timeout=30)
    environment=configuration(stage)
    return dict(platform=plan['qualifiedPlatform'],artifacts=origins,debianArchives=debian,planHash=file_hash(PLAN),
                externalRequirements=['Commercial provider licenses','macOS/Windows-only native targets','Caller-authorised Android/USB/logic-analyser devices']),environment
