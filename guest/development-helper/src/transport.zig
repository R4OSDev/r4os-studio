//! SSH is a client of an independent console watchdog. An explicit console
//! host prevents SSH-console inheritance; no SCM registration is required.
const std = @import("std");
const r4os = @import("r4os");
const control = @import("control.zig");
const abi = r4os.abi;

pub fn paths(parent: []const u8, instance: []const u8, request: *[256:0]u8, response: *[256:0]u8) bool {
    _ = std.fmt.bufPrintZ(request, "{s}\\Q{s}.JSN", .{ parent, instance[0..7] }) catch return false;
    _ = std.fmt.bufPrintZ(response, "{s}\\A{s}.JSN", .{ parent, instance[0..7] }) catch return false;
    return true;
}
pub fn readFile(sys: r4os.r4sys.Context, path: [*:0]const u8, buffer: []u8) i32 {
    const info = sys.fileInfo(path) orelse return -1;
    if (info.exists == 0 or info.is_dir != 0 or info.size > buffer.len) return -1;
    var offset: usize = 0;
    const size: usize = @intCast(info.size);
    while (offset < size) {
        const n = sys.fileReadAt(path, @intCast(offset), buffer[offset..size]);
        if (n <= 0 or @as(usize, @intCast(n)) > size - offset) return -1;
        offset += @intCast(n);
    }
    return @intCast(offset);
}

pub fn publish(sys: r4os.r4sys.Context, path: [*:0]const u8, instance: []const u8, sequence: u32, success: bool, value: anytype) bool {
    var memory: [65536]u8 = undefined;
    var allocator = std.heap.FixedBufferAllocator.init(&memory);
    const json = std.json.Stringify.valueAlloc(allocator.allocator(), .{
        .version = @as(u32, 1), .instance = instance, .sequence = sequence, .success = success, .result = value,
    }, .{}) catch return false;
    return sys.fileWrite(path, json) >= 0;
}

fn startupFailure(sys: r4os.r4sys.Context, instance: []const u8, module_path: []const u8,
    phase: []const u8, raw: i32, cleanup_confirmed: bool, exit_code: i32) i32 {
    control.emit(sys, instance, 0, false, .{ .startupFailureVersion = @as(u32, 1),
        .@"error" = "The guest controller could not initialize its independent watchdog.",
        .phase = phase, .rawCode = raw, .modulePath = module_path,
        .applicationStarted = false, .startupCleanupConfirmed = cleanup_confirmed });
    return exit_code;
}

pub fn serve(app: *r4os.App, instance: []const u8, module_path: []const u8) i32 {
    const sys = app.system();
    var relay_handle: abi.ProgramProcessHandle = .{};
    const own_status = sys.programOpenHandle(@intCast(app.raw.instance_id), &relay_handle);
    if (own_status != 0) return startupFailure(sys, instance, module_path, "relay_identity", own_status, true, 81);
    const slash = std.mem.lastIndexOfScalar(u8, module_path, '\\') orelse return 81;
    const parent = module_path[0..slash];
    var request: [256:0]u8 = .{0} ** 256;
    var response: [256:0]u8 = .{0} ** 256;
    var path: [256:0]u8 = .{0} ** 256;
    var journal: [256:0]u8 = .{0} ** 256;
    if (!paths(parent, instance, &request, &response)) return 81;
    _ = std.fmt.bufPrintZ(&path, "{s}\\STHELP.R4X", .{parent}) catch return 81;
    _ = std.fmt.bufPrintZ(&journal, "{s}\\B{s}.JSN", .{ parent, instance[0..7] }) catch return 81;
    for ([_][*:0]const u8{ &request, &response, &journal }) |file| {
        var info: abi.FileInfo = .{};
        const status = sys.fileInfoRaw(file, &info);
        if (status < 0) return startupFailure(sys, instance, module_path, "mailbox_identity", status, false, 82);
        if (status != 0 or info.exists != 0) return startupFailure(sys, instance, module_path, "mailbox_collision", status, false, 82);
    }
    const desk = app.desktop() orelse return startupFailure(sys, instance, module_path, "watchdog_capability", -1, true, 83);
    if (!desk.hasFn("program_spawn_with_console_host_handle"))
        return startupFailure(sys, instance, module_path, "watchdog_capability", -1, true, 83);
    var relay_generation: [24]u8 = undefined;
    const relay_generation_text = std.fmt.bufPrint(&relay_generation, "{d}", .{relay_handle.generation}) catch return 81;
    if (!publish(sys, &journal, instance, 0, true, .{ .startupVersion = @as(u32, 1), .phase = "watchdog_intent",
        .relayInstanceId = relay_handle.instance_id, .relayGeneration = relay_generation_text,
        .modulePath = module_path, .applicationStarted = false }))
        return startupFailure(sys, instance, module_path, "watchdog_intent", -1, true, 83);
    var args: [43:0]u8 = .{0} ** 43;
    _ = std.fmt.bufPrintZ(&args, "{s} watch", .{instance}) catch return 81;
    const resources = r4os.Resources{ .sys = sys };
    const launched = resources.spawnWithConsoleHost(.{ .ptr = &path,
        .len = @intCast(std.mem.sliceTo(&path, 0).len) }, &args, .console, .terminal_mode);
    // The public handle-spawn contract is atomic on failure. Never retry it.
    const spawned = switch (launched) {
        .process => |process| process,
        .failure => |raw| return startupFailure(sys, instance, module_path, "watchdog_spawn", raw, true, 83),
    };
    if (!spawned.valid()) return startupFailure(sys, instance, module_path, "watchdog_identity", -1, false, 84);
    var spawned_generation: [24]u8 = undefined;
    const spawned_generation_text = std.fmt.bufPrint(&spawned_generation, "{d}", .{spawned.generation}) catch
        return startupFailure(sys, instance, module_path, "watchdog_identity", -1, false, 84);
    if (!publish(sys, &journal, instance, 0, true, .{ .startupVersion = @as(u32, 1), .phase = "watchdog_started",
        .relayInstanceId = relay_handle.instance_id, .relayGeneration = relay_generation_text,
        .watchdogInstanceId = spawned.raw, .watchdogGeneration = spawned_generation_text,
        .modulePath = module_path, .applicationStarted = false }))
        return startupFailure(sys, instance, module_path, "watchdog_journal", -1, false, 84);
    var handshake_ok = false;
    var daemon: abi.ProgramProcessHandle = .{};
    var daemon_generation: [24]u8 = undefined;
    var daemon_generation_len: usize = 0;
    for (0..500) |_| {
        var frame: [12288]u8 = undefined;
        const n = readFile(sys, &response, &frame);
        if (n > 0) {
            var arena: [24576]u8 = undefined;
            var allocator = std.heap.FixedBufferAllocator.init(&arena);
            if (std.json.parseFromSlice(std.json.Value, allocator.allocator(), frame[0..@intCast(n)], .{})) |parsed| {
                const value = parsed.value;
                if (value == .object and value.object.get("instance") != null and
                    value.object.get("sequence") != null and value.object.get("success") != null) {
                    const nonce = value.object.get("instance").?;
                    const seq = value.object.get("sequence").?;
                    if (nonce == .string and std.mem.eql(u8, nonce.string, instance) and seq == .integer and seq.integer == 0) {
                        const result = value.object.get("result") orelse return 85;
                        if (result != .object) return 85;
                        const id_value = result.object.get("daemonInstanceId") orelse return 85;
                        const generation_value = result.object.get("daemonGeneration") orelse return 85;
                        if (id_value != .integer or id_value.integer < 1 or id_value.integer > 4294967295 or
                            generation_value != .string or generation_value.string.len > daemon_generation.len) return 85;
                        daemon.instance_id = @intCast(id_value.integer);
                        daemon.generation = std.fmt.parseInt(u64, generation_value.string, 10) catch return 85;
                        if (daemon.instance_id != spawned.raw or daemon.generation != spawned.generation)
                            return startupFailure(sys, instance, module_path, "watchdog_handshake_identity", -1, false, 85);
                        daemon_generation_len = generation_value.string.len;
                        @memcpy(daemon_generation[0..daemon_generation_len], generation_value.string);
                        handshake_ok = true;
                        break;
                    }
                }
            } else |_| {}
        }
        sys.sleepTicks(1);
    }
    if (!handshake_ok) return startupFailure(sys, instance, module_path, "watchdog_handshake", -1, false, 85);
    control.emit(sys, instance, 0, true, .{ .interface = "r4os-studio-guest", .controlVersion = @as(u32, 2),
        .desktopAdoptionVersion = @as(u32, 1),
        .desktopEvidenceVersion = @as(u32, 1),
        .desktopEvidenceRecoveryVersion = @as(u32, 1),
        .windowControlVersion = @as(u32, 1),
        .guiFrameBindingVersion = @as(u32, 1),
        .guiInputVersion = @as(u32, 2),
        .editorShortcutVersion = @as(u32, 1),
        .keyPlanVersion = @as(u32, 1),
        .desktopLinkVersion = @as(u32, 1),
        .gestureVersion = @as(u32, 1),
        .dragInterruptVersion = @as(u32, 1),
        .watchdogVersion = @as(u32, 1), .bootstrapRemoved = true, .watchdogInstanceId = daemon.instance_id,
        .watchdogLaunchVersion = @as(u32, 2), .bootstrapUsed = false,
        .watchdogGeneration = daemon_generation[0..daemon_generation_len],
        .receiptFile = std.mem.sliceTo(&response, 0), .modulePath = module_path });
    var line: [4096]u8 = undefined;
    var length: usize = 0;
    var sequence: u32 = 0;
    const born = sys.monotonicNanoseconds() orelse return 86;
    var heartbeat = born;
    while (true) {
        const current = sys.monotonicNanoseconds() orelse return 86;
        if (current - heartbeat > 15_000_000_000 or current - born > 315_000_000_000 or sys.programShouldClose()) return 87;
        const key = sys.readKey();
        if (key == 0) { sys.sleepTicks(1); continue; }
        if (key != '\r' and key != '\n') {
            if (length == line.len) return 88;
            line[length] = key; length += 1; continue;
        }
        if (length == 0) continue;
        var arena: [24576]u8 = undefined;
        var allocator = std.heap.FixedBufferAllocator.init(&arena);
        const parsed = std.json.parseFromSlice(control.Request, allocator.allocator(), line[0..length], .{}) catch return 89;
        const req = parsed.value;
        if (req.version != 1 or !std.mem.eql(u8, req.instance, instance) or req.sequence != sequence + 1) return 90;
        sequence = req.sequence; heartbeat = current;
        // The relay supplies its own native identity, never caller-provided
        // identity fields. The watchdog can abort gestures when SSH ends.
        var bound = req;
        bound.relayInstanceId = relay_handle.instance_id;
        bound.relayGeneration = relay_handle.generation;
        const bound_request = std.json.Stringify.valueAlloc(allocator.allocator(), bound, .{}) catch return 91;
        if (bound_request.len > 4096 or sys.fileWrite(&request, bound_request) < 0) return 91;
        length = 0;
        var received = false;
        for (0..500) |_| {
            var frame: [12288]u8 = undefined;
            const n = readFile(sys, &response, &frame);
            if (n > 0) {
                var response_arena: [32768]u8 = undefined;
                var response_allocator = std.heap.FixedBufferAllocator.init(&response_arena);
                const Envelope = struct { version: u32, instance: []const u8, sequence: u32, success: bool };
                if (std.json.parseFromSlice(Envelope, response_allocator.allocator(), frame[0..@intCast(n)], .{ .ignore_unknown_fields = true })) |answer| {
                    const value = answer.value;
                    if (value.version == 1 and std.mem.eql(u8, value.instance, instance) and value.sequence == sequence) {
                        if (std.mem.eql(u8, req.operation, "finish")) {
                            const Finished = struct { result: struct { closed: bool, serviceRemoved: bool } };
                            const finished = std.json.parseFromSlice(Finished, response_allocator.allocator(), frame[0..@intCast(n)], .{ .ignore_unknown_fields = true }) catch return 94;
                            if (!value.success or !finished.value.result.closed or !finished.value.result.serviceRemoved) {
                                sys.write(frame[0..@intCast(n)]); sys.println(""); return 94;
                            }
                            var ended = false;
                            for (0..300) |_| {
                                var process_info: abi.ProgramInstanceInfo = .{};
                                const code = sys.programHandleStatus(&daemon, &process_info);
                                if (code == abi.program_handle_error_not_found or code == abi.program_handle_error_stale or
                                    (code == 0 and process_info.state == @intFromEnum(abi.ProgramInstanceState.done))) {
                                    ended = true; break;
                                }
                                sys.sleepTicks(1);
                            }
                            control.emit(sys, instance, sequence, ended, .{ .closed = ended,
                                .serviceRemoved = true, .watchdogRemoved = ended, .bootstrapRemoved = true });
                            return if (ended) 0 else 92;
                        }
                        sys.write(frame[0..@intCast(n)]); sys.println(""); received = true; break;
                    }
                } else |parse_error| {
                    if (parse_error == error.OutOfMemory) {
                        control.emit(sys, instance, sequence, false, .{ .@"error" = "The bounded guest response parser ran out of memory." }); return 94;
                    }
                }
            }
            sys.sleepTicks(1);
        }
        if (!received) return 93;
    }
}
