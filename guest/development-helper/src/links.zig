//! One original native own-link operation. Prepare is not Activate; the host
//! saves the complete canonical request before the single activation call.
const std = @import("std");
const r4os = @import("r4os");
const a = r4os.abi;
const native = r4os.desktop_links;

pub fn decode(text: []const u8) ?native.Request {
    var value: native.Request = .{};
    if ((std.base64.standard.Decoder.calcSizeForSlice(text) catch return null) != @sizeOf(native.Request)) return null;
    std.base64.standard.Decoder.decode(std.mem.asBytes(&value), text) catch return null;
    return value;
}

pub const Controller = struct {
    sys: r4os.r4sys.Context,
    own: a.ProgramProcessHandle,
    prepared: ?native.Request = null,
    submitted: bool = false,
    last: ?native.Reply = null,

    pub fn prepare(self: *Controller, intent: []const u8, path: []const u8, bytes: []const u8) native.Call {
        if (self.prepared != null or self.submitted or intent.len != 36 or
            path.len != 28 or !std.mem.startsWith(u8, path, "C:\\R4OS\\DESKTOP\\S") or
            !std.mem.endsWith(u8, path, ".LNK")) return .{ .failure = a.desktop_link_result_invalid };
        for (path[17..24]) |c| if (!std.ascii.isHex(c)) return .{ .failure = a.desktop_link_result_invalid };
        var hash: [32]u8 = undefined;
        std.crypto.hash.sha2.Sha256.hash(intent, &hash, .{});
        const key: [3]u64 = .{ std.mem.readInt(u64, hash[0..8], .little),
            std.mem.readInt(u64, hash[8..16], .little), std.mem.readInt(u64, hash[16..24], .little) };
        const client = native.Client{ .sys = self.sys };
        const scoped = client.scope();
        if (scoped != .reply or !native.supported(&scoped.reply)) return .{ .failure = a.desktop_link_result_unavailable };
        const q = native.binding(scoped.reply.request.token, self.own, key,
            self.sys.ticks() +| self.sys.ticksFromMilliseconds(30000), path, bytes) orelse return .{ .failure = a.desktop_link_result_invalid };
        const result = client.prepare(q);
        if (result == .reply and result.reply.result == 0 and result.reply.phase == a.desktop_link_phase_prepared and
            result.reply.request.token.serial != 0) self.prepared = result.reply.request;
        if (result == .reply) self.last = result.reply;
        return result;
    }

    pub fn matches(self: *const Controller, text: []const u8) bool {
        const request = decode(text) orelse return false;
        const original = self.prepared orelse return false;
        return std.meta.eql(request, original);
    }

    pub fn activate(self: *Controller, text: []const u8) native.Call {
        if (self.submitted or !self.matches(text)) return .{ .failure = a.desktop_link_result_invalid };
        self.submitted = true;
        self.last = null;
        const client = native.Client{ .sys = self.sys };
        const result = client.activate(self.prepared.?);
        if (result == .reply) self.last = result.reply;
        return result;
    }

    pub fn status(self: *Controller) native.Call {
        const request = self.prepared orelse return .{ .failure = a.desktop_link_result_unavailable };
        const client = native.Client{ .sys = self.sys };
        const result = client.status(request);
        if (result == .reply) self.last = result.reply;
        return result;
    }

    pub fn release(self: *Controller) native.Call {
        const request = self.prepared orelse return .{ .failure = a.desktop_link_result_unavailable };
        const client = native.Client{ .sys = self.sys };
        const result = client.release(request);
        if (result == .reply) self.last = result.reply;
        return result;
    }
};

fn number(allocator: std.mem.Allocator, value: u64) []const u8 {
    return std.fmt.allocPrint(allocator, "{d}", .{value}) catch "unavailable";
}
fn encoded(allocator: std.mem.Allocator, bytes: []const u8) []const u8 {
    const buffer = allocator.alloc(u8, std.base64.standard.Encoder.calcSize(bytes.len)) catch return "";
    return std.base64.standard.Encoder.encode(buffer, bytes);
}

fn send(sys: r4os.r4sys.Context, path: ?[*:0]const u8, instance: []const u8, sequence: u32, value: anytype) bool {
    if (path) |output| return @import("transport.zig").publish(sys, output, instance, sequence, true, value);
    @import("control.zig").emit(sys, instance, sequence, true, value);
    return true;
}

pub fn respond(sys: r4os.r4sys.Context, path: ?[*:0]const u8, instance: []const u8, sequence: u32, result: native.Call) bool {
    if (result == .failure) return send(sys, path, instance, sequence, .{ .transportError = result.failure });
    var memory: [8192]u8 = undefined;
    var storage = std.heap.FixedBufferAllocator.init(&memory);
    const allocator = storage.allocator(); const reply = result.reply; const q = reply.request;
    return send(sys, path, instance, sequence, .{
        .nativeRequest = encoded(allocator, std.mem.asBytes(&q)),
        .result = reply.result, .phase = reply.phase, .flags = reply.flags,
        .linkPath = std.mem.sliceTo(&q.link_path, 0), .linkContent = q.link_bytes[0..q.link_length],
        .serial = number(allocator, q.token.serial), .deadline = number(allocator, q.deadline),
        .ownerId = q.token.owner.instance_id, .ownerGeneration = number(allocator, q.token.owner.generation),
        .serviceId = q.token.service.instance_id, .serviceGeneration = number(allocator, q.token.service.generation),
        .epoch = .{ number(allocator, q.token.epoch[0]), number(allocator, q.token.epoch[1]), number(allocator, q.token.epoch[2]) },
        .intent = .{ number(allocator, q.token.intent[0]), number(allocator, q.token.intent[1]), number(allocator, q.token.intent[2]) },
        .desktopId = reply.desktop.instance_id, .desktopGeneration = number(allocator, reply.desktop.generation),
        .processId = reply.process.instance_id, .processGeneration = number(allocator, reply.process.generation),
        .resolvedPath = std.mem.sliceTo(&reply.resolved_path, 0), .resolvedArguments = std.mem.sliceTo(&reply.resolved_args, 0),
        .policy = reply.policy, .acceptedTick = number(allocator, reply.accepted_tick),
        .startedTick = number(allocator, reply.started_tick), .readyTick = number(allocator, reply.ready_tick),
        .cleanupTick = number(allocator, reply.cleanup_tick), .contentGeneration = number(allocator, reply.content_generation),
        .completion = .{ .processId = reply.completion.handle.instance_id,
            .processGeneration = number(allocator, reply.completion.handle.generation),
            .sequence = number(allocator, reply.completion.sequence), .flags = reply.completion.flags,
            .exitCode = reply.completion.exit_code, .exitReason = reply.completion.exit_reason },
    });
}

pub fn recover(sys: r4os.r4sys.Context, instance: []const u8, module_path: []const u8) i32 {
    const slash = std.mem.lastIndexOfScalar(u8, module_path, '\\') orelse return 96;
    var path: [256:0]u8 = .{0} ** 256;
    _ = std.fmt.bufPrintZ(&path, "{s}\\L{s}.BIN", .{ module_path[0..slash], instance[0..7] }) catch return 96;
    const info = sys.fileInfo(&path) orelse return 96;
    if (info.is_dir != 0 or info.size != @sizeOf(native.Request)) return 96;
    var request: native.Request = .{};
    if (sys.fileRead(&path, std.mem.asBytes(&request)) != @sizeOf(native.Request)) return 96;
    const client = native.Client{ .sys = sys };
    if (!respond(sys, null, instance, 0, client.status(request))) return 96;
    return 0;
}
