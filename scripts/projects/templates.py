"""Project skeletons use the selected SDK's canonical file maps and creator."""
import hashlib
import json

REVISION = 'templates-v6'


def revision(pins, variant=REVISION):
    return hashlib.sha256((json.dumps(pins, sort_keys=True) + ':' + variant).encode()).hexdigest()

BUILD = '''const std = @import("std");
pub fn build(b: *std.Build) void {
    const sdk_build = b.lazyImport(@This(), "r4os_sdk") orelse return;
    const dependency = b.dependencyFromBuildZig(sdk_build, .{});
    const sdk = sdk_build.sdk(b, dependency, .{});
    _ = sdk.addR4MF(b.path("module.R4MF"));
}
'''


def render(context, directory, project, include_agents=True):
    from sdk import TYPES
    from toolset import render as sdk_render
    result = sdk_render(context, directory, project, next(value for value in TYPES if value[0] == project['template']))
    if include_agents:
        from project_agents import ensure_at
        ensure_at(directory, project)
    return result


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def hashes(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Unexpected symbolic link in project files.')
        if path.is_file():
            result[str(path.relative_to(directory))] = digest(path)
    return result
