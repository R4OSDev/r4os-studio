//! Own DESKRUN delegation only. Opaque native requests are prepared before the
//! host persists/submits them; status never repeats a window command.
const std = @import("std");
const r4os = @import("r4os");
const a = r4os.abi;
const native = r4os.desktop_actions;

fn decode(comptime T: type, text: []const u8) ?T {
    var value: T = .{};
    if ((std.base64.standard.Decoder.calcSizeForSlice(text) catch return null) != @sizeOf(T)) return null;
    std.base64.standard.Decoder.decode(std.mem.asBytes(&value), text) catch return null;
    return value;
}

pub const Controller = struct {
    sys: r4os.r4sys.Context,
    own: a.ProgramProcessHandle,
    token: ?native.Token = null,
    prepared: ?native.Request = null,
    submitted: bool = false,
    frame_confirmed: bool = false,
    last: ?native.Reply = null,
    outcome: ?native.Reply = null,

    pub fn settled(self: *const Controller) bool {
        if (!self.submitted) return true;
        const expected = self.prepared orelse return false;
        const reply = self.outcome orelse return false;
        if (!std.meta.eql(reply.request, expected)) return false;
        return self.frame_confirmed or
            (reply.phase == a.desktop_action_phase_rejected and reply.result < 0);
    }

    fn observeOutcome(self: *Controller, reply: native.Reply) void {
        const expected = self.prepared orelse return;
        if (!self.submitted or !std.meta.eql(reply.request, expected)) return;
        self.outcome = reply;
        if (native.frameReady(&reply)) self.frame_confirmed = true;
    }

    pub fn bind(self: *Controller, scope: a.DesktopEvidenceToken, grant: u64, process: a.ProgramProcessHandle) native.Call {
        if (self.token != null) return .{ .failure = a.desktop_action_result_invalid };
        const client = native.Client{ .sys = self.sys };
        const initial: native.Token = .{ .window = .{ .service = scope.broker }, .request = scope.request,
            .controller = self.own, .epoch = scope.epoch, .grant = grant, .rights = a.desktop_action_right_all };
        const result = client.status(initial, 0);
        if (result == .reply and result.reply.result == 0) {
            const token = result.reply.request.token;
            if (!std.meta.eql(token.window.owner, process) or token.window.serial == 0 or token.grant == 0)
                return .{ .failure = a.desktop_action_result_invalid };
            self.token = token; self.last = result.reply;
        }
        return result;
    }

    pub fn prepare(self: *Controller, operation: u64, kind: []const u8, width: i32, height: i32) ?native.Request {
        const token = self.token orelse return null;
        if (operation == 0) return null;
        if (self.prepared) |old| if (operation == old.operation) return null;
        if (!self.settled()) return null;
        const native_kind: u32 = if (std.mem.eql(u8, kind, "resize")) a.desktop_action_kind_resize else
            if (std.mem.eql(u8, kind, "minimize")) a.desktop_action_kind_minimize else
            if (std.mem.eql(u8, kind, "restore")) a.desktop_action_kind_restore else return null;
        if (native_kind == a.desktop_action_kind_resize) {
            if (width < 64 or width > 1280 or height < 64 or height > 1024) return null;
        } else if (width != 0 or height != 0) return null;
        const client = native.Client{ .sys = self.sys };
        const observed = client.status(token, 0);
        if (observed != .reply or observed.reply.result != 0 or
            !std.meta.eql(observed.reply.current.window, token.window)) return null;
        self.last = observed.reply;
        const request: native.Request = .{ .token = token, .operation = operation,
            .deadline = self.sys.ticks() +| self.sys.ticksFromMilliseconds(2500),
            .kind = native_kind, .width = width, .height = height,
            .x = if (native_kind == a.desktop_action_kind_resize) observed.reply.current.info.client_x else 0,
            .y = if (native_kind == a.desktop_action_kind_resize) observed.reply.current.info.client_y else 0 };
        self.prepared = request; self.submitted = false;
        return request;
    }

    pub fn command(self: *Controller, opaque_request: []const u8) native.Call {
        const request = decode(native.Request, opaque_request) orelse return .{ .failure = a.desktop_action_result_invalid };
        const expected = self.prepared orelse return .{ .failure = a.desktop_action_result_invalid };
        if (self.submitted or !std.meta.eql(request, expected)) return .{ .failure = a.desktop_action_result_invalid };
        self.submitted = true;
        self.frame_confirmed = false;
        self.outcome = null;
        // Clear a previous receipt before an uncertain new transport result.
        self.last = null;
        const client = native.Client{ .sys = self.sys };
        const result = client.command(request);
        if (result == .reply) { self.last = result.reply; self.observeOutcome(result.reply); }
        return result;
    }

    pub fn matchesPrepared(self: *const Controller, opaque_request: []const u8, kind: u32, minimum_milliseconds: u32) bool {
        const request = decode(native.Request, opaque_request) orelse return false;
        const expected = self.prepared orelse return false;
        const now = self.sys.ticks();
        return !self.submitted and request.kind == kind and std.meta.eql(request, expected) and
            request.deadline > now and request.deadline - now >= self.sys.ticksFromMilliseconds(minimum_milliseconds);
    }

    pub fn status(self: *Controller, operation: u64) native.Call {
        const token = self.token orelse return .{ .failure = a.desktop_action_result_unavailable };
        // Scope status cannot replace the outstanding operation's receipt or
        // unlock another command after an uncertain effect.
        if (!self.settled() and operation == 0) return .{ .failure = a.desktop_action_result_invalid };
        if (operation != 0 and (self.prepared == null or self.prepared.?.operation != operation))
            return .{ .failure = a.desktop_action_result_invalid };
        const client = native.Client{ .sys = self.sys };
        const result = client.status(token, operation);
        if (result == .reply) {
            self.last = result.reply;
            self.observeOutcome(result.reply);
        }
        return result;
    }

    pub fn release(self: *Controller) native.Call {
        const token = self.token orelse return .{ .failure = a.desktop_action_result_unavailable };
        const client = native.Client{ .sys = self.sys };
        return client.release(token);
    }
};

fn number(allocator: std.mem.Allocator, value: u64) []const u8 {
    return std.fmt.allocPrint(allocator, "{d}", .{value}) catch "unavailable";
}
fn encoded(allocator: std.mem.Allocator, bytes: []const u8) []const u8 {
    const buffer = allocator.alloc(u8, std.base64.standard.Encoder.calcSize(bytes.len)) catch return "";
    return std.base64.standard.Encoder.encode(buffer, bytes);
}
const View = struct {
    identity: []const u8, windowId: u32, viewRevision: []const u8, frameGeneration: []const u8,
    compositionSerial: []const u8, inputRevision: []const u8, proofFlags: u32, geometry: a.GuiWindowInfo,
};
fn view(allocator: std.mem.Allocator, value: native.State) View {
    return .{ .identity = encoded(allocator, std.mem.asBytes(&value.window)), .windowId = value.window.window_id,
        .viewRevision = number(allocator, value.view_revision), .frameGeneration = number(allocator, value.frame_generation),
        .compositionSerial = number(allocator, value.composition_serial), .inputRevision = number(allocator, value.input_revision),
        .proofFlags = value.proof_flags, .geometry = value.info };
}

pub fn respond(sys: r4os.r4sys.Context, path: [*:0]const u8, instance: []const u8, sequence: u32, result: native.Call) bool {
    const publish = @import("transport.zig").publish;
    if (result == .failure) return publish(sys, path, instance, sequence, true, .{ .transportError = result.failure });
    var memory: [4096]u8 = undefined;
    var storage = std.heap.FixedBufferAllocator.init(&memory);
    const allocator = storage.allocator(); const reply = result.reply;
    return publish(sys, path, instance, sequence, true, .{
        .result = reply.result, .phase = reply.phase, .frameReady = native.frameReady(&reply),
        .token = encoded(allocator, std.mem.asBytes(&reply.request.token)),
        .nativeRequest = encoded(allocator, std.mem.asBytes(&reply.request)),
        .operationId = number(allocator, reply.request.operation), .deadline = number(allocator, reply.request.deadline),
        .kind = reply.request.kind, .appliedTick = number(allocator, reply.applied_tick),
        .applied = view(allocator, reply.applied), .current = view(allocator, reply.current),
    });
}

pub fn prepared(sys: r4os.r4sys.Context, path: [*:0]const u8, instance: []const u8, sequence: u32, request: native.Request) bool {
    var buffer: [256]u8 = undefined;
    return @import("transport.zig").publish(sys, path, instance, sequence, true, .{
        .nativeRequest = std.base64.standard.Encoder.encode(buffer[0..std.base64.standard.Encoder.calcSize(@sizeOf(native.Request))], std.mem.asBytes(&request)),
    });
}
