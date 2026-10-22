//! Short-lived SCM bootstrap. An explicit console host has no inherited
//! SSH console parent; the watchdog survives both bootstrap and SSH exit.
const std = @import("std");
const r4os = @import("r4os");
pub fn run(app: *r4os.App) i32 {
    const sys = app.system();
    const instance = app.args();
    if (instance.len != 36) return 64;
    for (instance) |c| if (!(std.ascii.isHex(c) or c == '-')) return 64;
    var module: [256]u8 = undefined;
    const n = sys.programModulePath(&module);
    if (n <= 0) return 65;
    const slash = std.mem.lastIndexOfScalar(u8, module[0..@intCast(n)], '\\') orelse return 65;
    var path: [256:0]u8 = .{0} ** 256;
    var args: [43:0]u8 = .{0} ** 43;
    _ = std.fmt.bufPrintZ(&path, "{s}\\STHELP.R4X", .{module[0..slash]}) catch return 66;
    _ = std.fmt.bufPrintZ(&args, "{s} watch", .{instance}) catch return 66;
    const resources = r4os.Resources{ .sys = sys };
    const process = switch (resources.spawnWithConsoleHost(.{ .ptr = &path,
        .len = @intCast(std.mem.sliceTo(&path, 0).len) }, &args, .console, .terminal_mode)) {
        .process => |p| p, else => return 67,
    };
    return if (process.valid()) 0 else 68;
}
