const std = @import("std");
const artifact = @import("r4u_artifact");
const contract = artifact.contract;
const Reader = struct {
    file: std.Io.File,
    io: std.Io,
    pub fn readAt(self: Reader, offset: u64, out: []u8) bool {
        const got = self.file.readPositionalAll(self.io, out, offset) catch return false;
        return got == out.len;
    }
};
pub fn main(init: std.process.Init) !void {
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 4) return error.BadArguments;
    const file = try std.Io.Dir.cwd().openFile(init.io, args[1], .{});
    defer file.close(init.io);
    const info = try file.stat(init.io);
    if (info.kind != .file or info.size > 128 * 1024 * 1024) return error.BadArtifact;
    const identity = artifact.inspect(Reader{ .file = file, .io = init.io }, info.size) orelse return error.MissingNativeArtifactIdentity;
    var buffer: [1024]u8 = undefined;
    const target = contract.canonicalInventoryTarget(&buffer, args[2]) orelse return error.BadTarget;
    if (contract.isManagedStateTarget(target)) return error.ManagedStateTarget;
    const expected = contract.componentKindForPayload(args[3], target) orelse return error.UnsupportedPayloadKind;
    if (identity.kind != expected) return error.ArtifactKindMismatch;
    const value = try std.json.Stringify.valueAlloc(init.arena.allocator(), .{
        .schema = @as(u32, 1),
        .kind = identity.kind.text(),
        .name = identity.nameText(),
        .version = identity.versionText(),
        .target = target,
        .activation = contract.installModeFor(identity.kind, target).text(),
        .priority = contract.priorityFor(identity.kind).text(),
    }, .{});
    std.debug.print("{s}\n", .{value});
}
