"""Run the selected SDK's declared Rust project driver."""
from sdk_host import command


def build(context, directory, output=None):
    output = output or directory / 'build'
    args = [context['runner'], '-NoLogo', '-NoProfile', '-File',
            context['paths']['sdk'] / context['capabilities']['project_creation']['rust_builder'], '-ProjectRoot', directory,
            '-SdkRoot', context['paths']['sdk'], '-ContractRoot', context['paths']['contract'],
            '-LibrariesRoot', context['paths']['libraries'], '-ToolsRoot', context['sdkTools']['tools'],
            '-InstallRoot', context['paths']['install'], '-ZigRoot', context['paths']['zig'],
            '-CacheRoot', context['cache'] / 'rust-build-cache', '-OutputRoot', output]
    return command(args, context['env'], context['cache'], timeout=600)
