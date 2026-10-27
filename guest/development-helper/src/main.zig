//! Studio-owned guest adapter. Only public pinned SDK interfaces are used.
const std = @import("std");
const r4os = @import("r4os");

pub fn r4_app_main(app: *r4os.App) i32 {
    const sys = app.system();
    const arguments = app.args();
    const watchdog = arguments.len == 42 and std.mem.endsWith(u8, arguments, " watch");
    const persistent = arguments.len == 42 and std.mem.endsWith(u8, arguments, " serve");
    const instance = if (persistent or watchdog) arguments[0..36] else arguments;
    if (instance.len != 36) return 64;
    for (instance) |c| if (!(std.ascii.isHex(c) or c == '-')) return 64;
    const resources = r4os.Resources{ .sys = sys };
    if (!resources.available() or !sys.hasFn("file_read_at")) return 65;
    var memory: [8192]u8 = undefined;
    var allocator = std.heap.FixedBufferAllocator.init(&memory);
    var path: [256]u8 = undefined;
    const count = sys.programModulePath(&path);
    if (count <= 0) return 66;
    if (watchdog) return @import("control.zig").watch(app, instance);
    if (persistent) return @import("control.zig").serve(app, instance, path[0..@intCast(count)]);
    const response = .{
        .version = @as(u32, 1),
        .requestId = instance,
        .instance = instance,
        .success = true,
        .result = .{
            .interface = "r4os-studio-guest",
            .protocol = @as(u32, 1),
            .mode = "qualification",
            .controlVersion = @as(u32, 2),
            .watchdogVersion = @as(u32, 1),
            .modulePath = path[0..@intCast(count)],
            .processHandles = resources.available(),
            .consoleInput = true,
            .guiInput = true,
            .guiInputVersion = @as(u32, 2),
            .guiFrameBindingVersion = @as(u32, 1),
            .nativeDesktopLaunch = false,
            .desktopAdoptionVersion = @as(u32, 1),
            .exchangeRunVersion = @as(u32, 1),
            .argumentBytes = @as(u32, 127),
            .serviceSelfTest = true,
            .consoleRead = true,
            .completionRead = sys.hasFn("program_completion_read"),
            .fileRead = sys.hasFn("file_read_at"),
            .serviceControl = sys.hasFn("service_install") and sys.hasFn("service_start") and
                sys.hasFn("service_stop") and sys.hasFn("service_status") and sys.hasFn("service_remove"),
            .monotonicClock = sys.monotonicNanoseconds() != null,
        },
    };
    const output = std.json.Stringify.valueAlloc(allocator.allocator(), response, .{}) catch return 67;
    sys.write(output);
    sys.println("");
    return 0;
}
