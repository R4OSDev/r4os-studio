"""Project skeletons use the selected SDK's canonical file maps and creator."""
import hashlib
import json

REVISION = 'templates-v4'


def revision(pins):
    return hashlib.sha256((json.dumps(pins, sort_keys=True) + ':' + REVISION).encode()).hexdigest()

BUILD = '''const std = @import("std");
pub fn build(b: *std.Build) void {
    const sdk_build = b.lazyImport(@This(), "r4os_sdk") orelse return;
    const dependency = b.dependencyFromBuildZig(sdk_build, .{});
    const sdk = sdk_build.sdk(b, dependency, .{});
    _ = sdk.addR4MF(b.path("module.R4MF"));
}
'''


def render(context, directory, project):
    from sdk import TYPES
    from toolset import render as sdk_render
    return sdk_render(context, directory, project, next(value for value in TYPES if value[0] == project['template']))


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
