//! Persistent controller for one owned R4OS execution. No shell commands.
const std = @import("std");
const r4os = @import("r4os");
const abi = r4os.abi;
pub const Request = struct {
    version: u32 = 1,
    instance: []const u8,
    sequence: u32,
    operation: []const u8,
    role: []const u8 = "",
    arguments: []const u8 = "",
    timeoutSeconds: u32 = 60,
    input: []const u8 = "",
    generation: []const u8 = "",
    instanceId: u32 = 0,
    brokerInstanceId: u32 = 0,
    brokerGeneration: []const u8 = "",
    serviceName: []const u8 = "",
    inputKind: []const u8 = "text",
    key: u32 = 0,
    keyRepeat: u32 = 1,
    x: i32 = 0,
    y: i32 = 0,
    expectedRevision: u32 = 0,
    frameBindingVersion: u32 = 0,
    expectedWindowId: i32 = -1,
    expectedWindowWidth: i32 = 0,
    expectedWindowHeight: i32 = 0,
};

pub fn emit(sys: r4os.r4sys.Context, instance: []const u8, sequence: u32, success: bool, result: anytype) void {
    var memory: [65536]u8 = undefined;
    var allocator = std.heap.FixedBufferAllocator.init(&memory);
    const output = std.json.Stringify.valueAlloc(allocator.allocator(), .{
        .version = @as(u32, 1), .instance = instance, .sequence = sequence,
        .success = success, .result = result,
    }, .{}) catch return;
    sys.write(output);
    sys.println("");
}

const State = struct {
    state: []const u8 = "ready",
    instanceId: u32 = 0,
    generation: []const u8 = "0",
    windowId: i32 = -1,
    windowVisible: bool = false,
    windowFocused: bool = false,
    windowWidth: i32 = 0,
    windowHeight: i32 = 0,
    exitCode: ?i32 = null,
    exitReason: ?u8 = null,
    completionSequence: ?u64 = null,
    serviceState: ?u32 = null,
    serviceName: ?[]const u8 = null,
    serviceEndpointReady: bool = false,
    outputBase64: []const u8 = "",
    outputIncomplete: bool = false,
    stopReason: ?[]const u8 = null,
    closeConfirmed: bool = false,
    inputAccepted: ?u32 = null,
    guiRevision: u32 = 0,
    serviceCheckPassed: ?bool = null,
    serviceResponseBase64: []const u8 = "",
    exitEvidenceUnavailable: bool = false,
};

const Controller = struct {
    sys: r4os.r4sys.Context,
    desk: r4os.r4desk.Context,
    path: [256:0]u8 = .{0} ** 256,
    service: [32:0]u8 = .{0} ** 32,
    process: ?r4os.app_resources.ProcessHandle = null,
    desktop_broker: ?r4os.app_resources.ProcessHandle = null,
    started: bool = false,
    service_owned: bool = false,
    console_role: bool = false,
    service_removed: bool = true,
    started_ns: u64 = 0,
    deadline_ns: u64 = 0,
    closing_ns: u64 = 0,
    stopped: ?[]const u8 = null,
    completed: ?abi.ProgramProcessCompletion = null,
    output_cursor: u32 = 0,
    completion_initialized: bool = false,
    stream_cursor: u32 = 0,
    last_clear: u32 = 0,
    incomplete: bool = false,
    generation_buf: [24]u8 = undefined,
    output: [6145]u8 = undefined,
    encoded: [8196]u8 = undefined,
    service_response: [512]u8 = undefined,
    service_encoded: [684]u8 = undefined,
    mouse_pending: bool = false,
    state: State = .{},

    fn clock(self: *Controller) u64 { return self.sys.monotonicNanoseconds() orelse 0; }
    fn raw(self: *Controller) abi.ProgramProcessHandle {
        const p = self.process.?;
        return .{ .instance_id = p.raw, .generation = p.generation };
    }
    fn ownsService(self: *Controller) bool {
        if (!self.service_owned) return false;
        var detail: abi.ServiceDetail = .{};
        if (self.sys.serviceDetailByName(&self.service, &detail) != 0 or
            !std.ascii.eqlIgnoreCase(std.mem.sliceTo(&detail.path, 0), std.mem.sliceTo(&self.path, 0)) or
            detail.info.start_mode != abi.service_start_manual) return false;
        if (self.process) |*p| {
            if (detail.info.instance_id == 0) return detail.info.state == abi.service_state_stopped or detail.info.state == abi.service_state_failed;
            if (detail.info.instance_id != p.raw) return false;
            switch (p.status()) { .value => {}, else => return false }
        }
        return true;
    }
    fn start(self: *Controller, req: Request) bool {
        if (self.started or req.arguments.len > 127 or req.timeoutSeconds < 1 or req.timeoutSeconds > 300 or
            std.mem.indexOfScalar(u8, req.arguments, 0) != null) return false;
        const is_service = std.mem.eql(u8, req.role, "service");
        if (!is_service and !std.mem.eql(u8, req.role, "terminal")) return false;
        var args: [1025:0]u8 = .{0} ** 1025;
        @memcpy(args[0..req.arguments.len], req.arguments);
        self.console_role = std.mem.eql(u8, req.role, "terminal");
        const resources = r4os.Resources{ .sys = self.sys };
        self.started = true; // A refused/ambiguous start cannot be replayed.
        self.started_ns = self.clock();
        self.deadline_ns = self.started_ns + @as(u64, req.timeoutSeconds) * 1_000_000_000;
        if (is_service) {
            if (req.serviceName.len < 1 or req.serviceName.len > 31 or req.arguments.len > 95) return false;
            for (req.serviceName) |c| if (!(std.ascii.isAlphanumeric(c) or c == '_')) return false;
            @memset(&self.service, 0);
            @memcpy(self.service[0..req.serviceName.len], req.serviceName);
            self.state.serviceName = self.service[0..req.serviceName.len];
            var existing: abi.ServiceInfo = .{};
            if (self.sys.serviceStatus(&self.service, &existing) == 0) return false;
            var installed: abi.ServiceInfo = .{};
            if (self.sys.serviceInstall(&self.service, &self.path, &args, abi.service_start_manual, "Studio bounded development execution", &installed) != 0) return false;
            self.service_owned = true;
            self.service_removed = false;
            if (!self.ownsService()) return false;
            if (self.sys.serviceStart(&self.service, &installed) != 0 or installed.instance_id == 0) return false;
            self.process = switch (resources.openProcess(installed.instance_id)) {
                .process => |p| p, else => return false,
            };
        } else {
            const path = r4os.path.PathZ{ .ptr = &self.path, .len = @intCast(std.mem.sliceTo(&self.path, 0).len) };
            self.process = switch (resources.spawnWithConsoleHost(path, &args, .console, .terminal_mode)) {
                .process => |p| p, else => return false,
            };
        }
        self.state.instanceId = self.process.?.raw;
        self.state.generation = std.fmt.bufPrint(&self.generation_buf, "{d}", .{self.process.?.generation}) catch return false;
        self.state.state = "running";
        return true;
    }
    fn adoptDesktop(self: *Controller, req: Request) bool {
        if (self.started or req.instanceId == 0 or req.timeoutSeconds < 1 or req.timeoutSeconds > 300) return false;
        const generation = std.fmt.parseInt(u64, req.generation, 10) catch return false;
        if (generation == 0) return false;
        const process = r4os.app_resources.ProcessHandle{ .sys = self.sys, .raw = req.instanceId, .generation = generation };
        const broker_generation = std.fmt.parseInt(u64, req.brokerGeneration, 10) catch return false;
        // Only the exact DESKRUN receipt may supply this identity. Desktop owns
        // and reaps its child; a borrowed handle permits bounded close/kill and
        // completion reads without stealing native lifecycle ownership.
        if (req.brokerInstanceId == 0 or broker_generation == 0) return false;
        self.process = process;
        // A lost broker must not prevent cleanup of an already started child.
        // Its original receipt identity gates subsequent window observations.
        self.desktop_broker = .{ .sys = self.sys, .raw = req.brokerInstanceId, .generation = broker_generation };
        self.started = true;
        self.started_ns = self.clock();
        self.deadline_ns = self.started_ns + @as(u64, req.timeoutSeconds) * 1_000_000_000;
        self.state.instanceId = process.raw;
        self.state.generation = std.fmt.bufPrint(&self.generation_buf, "{d}", .{generation}) catch return false;
        self.state.state = "running";
        // Desktop owns window association and initial client resize. Studio
        // changes neither the application's entry point nor its paint calls.
        return true;
    }
    fn boundWindow(self: *Controller, req: Request) bool {
        self.windowState();
        if (!self.state.windowVisible or !self.state.windowFocused) return false;
        if (req.frameBindingVersion == 1) {
            return req.expectedWindowId == self.state.windowId and req.expectedWindowWidth > 0 and req.expectedWindowHeight > 0 and
                req.expectedWindowWidth == self.state.windowWidth and req.expectedWindowHeight == self.state.windowHeight;
        }
        return req.frameBindingVersion == 0 and req.expectedRevision == self.state.guiRevision;
    }
    fn guiEvents(self: *Controller, req: Request) bool {
        var points: [64]u32 = undefined;
        var count: usize = 0;
        if (std.mem.eql(u8, req.inputKind, "guiText")) {
            if (req.input.len == 0 or req.input.len > 256) return false;
            const view = std.unicode.Utf8View.init(req.input) catch return false;
            var iterator = view.iterator();
            while (iterator.nextCodepoint()) |point| {
                if (count == points.len or point < 32 or (point >= 127 and point < 160)) return false;
                points[count] = point; count += 1;
            }
        } else {
            if (req.keyRepeat < 1 or req.keyRepeat > 16) return false;
            const supported = switch (req.key) {
                ' '...'~', r4os.gui.Key.backspace, r4os.gui.Key.tab, r4os.gui.Key.enter, r4os.gui.Key.escape,
                r4os.gui.Key.delete, r4os.gui.Key.up, r4os.gui.Key.down, r4os.gui.Key.shift_tab,
                r4os.gui.Key.left, r4os.gui.Key.right, r4os.gui.Key.home, r4os.gui.Key.end,
                r4os.gui.Key.page_up, r4os.gui.Key.page_down => true,
                else => false,
            };
            if (!supported) return false;
            count = @intCast(req.keyRepeat);
            @memset(points[0..count], req.key);
        }
        self.state.inputAccepted = 0;
        const born = self.clock();
        if (born == 0) return false;
        for (points[0..count], 0..) |point, index| {
            const current = self.clock();
            if (current < born or current - born > 2_000_000_000) break;
            if (index > 0 and index % 8 == 0 and !self.boundWindow(req)) break;
            switch (self.process.?.status()) { .value => {}, else => break }
            var event = abi.GuiEvent{ .kind = @intFromEnum(abi.GuiEventKind.key_down),
                .window_id = self.state.windowId, .key = point, .tick = self.sys.ticks() };
            if (self.desk.guiPushEvent(self.process.?.raw, &event) < 0) break;
            self.state.inputAccepted = (self.state.inputAccepted orelse 0) + 1;
        }
        // A partial enqueue is an explicit receipt, never permission to replay.
        return true;
    }
    fn input(self: *Controller, req: Request) bool {
        if (self.process == null or self.completed != null or self.state.closeConfirmed or self.stopped != null or
            !std.mem.eql(u8, req.generation, self.state.generation) or req.input.len > 1024) return false;
        switch (self.process.?.status()) { .value => {}, else => return false }
        if (self.console_role) {
            if (!std.mem.eql(u8, req.inputKind, "text")) return false;
            const view = std.unicode.Utf8View.init(req.input) catch return false;
            var iterator = view.iterator(); var events: [64]abi.ConsoleInputEvent = undefined; var count: usize = 0;
            while (iterator.nextCodepoint()) |point| {
                if (count == events.len) return false;
                events[count] = .{ .kind = abi.console_input_event_text, .value = point }; count += 1;
            }
            const accepted = self.sys.consolePushEvents(self.raw(), events[0..count]);
            if (accepted < 0) return false;
            self.state.inputAccepted = @intCast(accepted); return true;
        }
        if (self.service_owned) return false;
        if (!self.boundWindow(req)) return false;
        if (std.mem.eql(u8, req.inputKind, "key") or std.mem.eql(u8, req.inputKind, "guiText")) return self.guiEvents(req);
        var event = abi.GuiEvent{ .window_id = self.state.windowId, .tick = self.sys.ticks() };
        if (!std.mem.eql(u8, req.inputKind, "click") or req.x < 0 or req.y < 0 or
            req.x >= self.state.windowWidth or req.y >= self.state.windowHeight) return false;
        event.kind = @intFromEnum(abi.GuiEventKind.mouse_down); event.x = req.x; event.y = req.y; event.buttons = 1;
        if (self.desk.guiPushEvent(self.process.?.raw, &event) < 0) return false;
        self.mouse_pending = true;
        event.kind = @intFromEnum(abi.GuiEventKind.mouse_up); event.buttons = 0;
        if (self.desk.guiPushEvent(self.process.?.raw, &event) < 0) { self.state.inputAccepted = 1; return true; }
        self.mouse_pending = false; self.state.inputAccepted = 2; return true;
    }
    fn serviceCheck(self: *Controller) void {
        self.state.serviceCheckPassed = false; self.state.serviceResponseBase64 = "";
        if (!self.ownsService() or self.process == null or self.state.closeConfirmed) return;
        const services = r4os.Services{ .sys = self.sys };
        var connection = switch (services.open(&self.service)) { .connection => |c| c, else => return };
        defer { _ = connection.close(); }
        switch (connection.call(1, "", &self.service_response, r4os.time_contract.timeoutFinite(.{ .nanoseconds = 500_000_000 }))) {
            .response => |response| {
                const length = std.base64.standard.Encoder.calcSize(response.bytes);
                self.state.serviceResponseBase64 = std.base64.standard.Encoder.encode(self.service_encoded[0..length], self.service_response[0..response.bytes]);
                self.state.serviceCheckPassed = true;
            }, else => {},
        }
    }

    fn stop(self: *Controller, reason: []const u8) void {
        if (self.stopped != null or self.completed != null) return;
        self.stopped = reason;
        self.state.stopReason = reason;
        self.closing_ns = self.clock();
        if (self.process) |*p| { _ = p.requestClose(); }
    }
    fn cleanup(self: *Controller) void {
        if (self.mouse_pending and self.process != null) {
            switch (self.process.?.status()) { .value => {
                var event = abi.GuiEvent{ .kind = @intFromEnum(abi.GuiEventKind.mouse_up), .window_id = self.state.windowId, .buttons = 0, .tick = self.sys.ticks() };
                _ = self.desk.guiPushEvent(self.process.?.raw, &event);
            }, else => {} }
            self.mouse_pending = false;
        }
        if (self.process) |*p| {
            if (p.valid() and self.completed == null) {
                _ = p.requestClose();
                switch (p.waitReady(r4os.time_contract.timeoutFinite(.{ .nanoseconds = 500_000_000 }))) {
                    .ready => {}, else => { _ = p.kill(); },
                }
                switch (p.waitReady(r4os.time_contract.timeoutFinite(.{ .nanoseconds = 2_000_000_000 }))) {
                    .ready => { if (p.owned) { _ = p.reap(); } }, else => {},
                }
            }
        }
        if (self.ownsService()) {
            var info: abi.ServiceInfo = .{};
            _ = self.sys.serviceStop(&self.service, &info, self.sys.ticksFromMilliseconds(1000));
            self.service_removed = self.sys.serviceRemove(&self.service) == 0;
        }
    }
    fn windowState(self: *Controller) void {
        self.state.windowVisible = false;
        self.state.windowFocused = false;
        self.state.guiRevision = if (self.process != null) self.desk.guiRevision(self.process.?.raw) else 0;
        if (self.state.windowId < 0 or self.process == null) return;
        const services = r4os.Services{ .sys = self.sys };
        var connection = switch (services.open("WINSVC")) { .connection => |c| c, else => return };
        defer { _ = connection.close(); }
        if (self.desktop_broker) |broker| {
            if (connection.info.instance_id != broker.raw) return;
            switch (broker.status()) { .value => {}, else => return }
        }
        var snapshot: abi.WindowServiceSnapshot = .{};
        switch (connection.call(abi.window_service_op_snapshot, "", std.mem.asBytes(&snapshot),
            r4os.time_contract.timeoutFinite(.{ .nanoseconds = 200_000_000 }))) {
            .response => |response| { if (response.bytes != @sizeOf(abi.WindowServiceSnapshot)) return; },
            else => return,
        }
        if (snapshot.magic != abi.window_service_snapshot_magic or snapshot.version != abi.window_service_snapshot_version) return;
        switch (self.process.?.status()) { .value => {}, else => return }
        if (self.desktop_broker) |broker| { switch (broker.status()) { .value => {}, else => return } }
        for (snapshot.records) |record| {
            if (record.instance_id != self.process.?.raw or record.window_id != self.state.windowId) continue;
            self.state.windowVisible = (record.flags & abi.window_service_flag_visible) != 0 and
                (record.flags & abi.window_service_flag_minimized) == 0;
            self.state.windowFocused = self.state.windowVisible and (record.flags & abi.window_service_flag_focused) != 0 and
                snapshot.status.focused_instance == self.process.?.raw;
            self.state.windowWidth = record.w;
            self.state.windowHeight = record.h;
            return;
        }
    }
    fn observe(self: *Controller) State {
        self.state.outputBase64 = "";
        if (self.mouse_pending and self.process != null) {
            switch (self.process.?.status()) { .value => {
                var release_event = abi.GuiEvent{ .kind = @intFromEnum(abi.GuiEventKind.mouse_up), .window_id = self.state.windowId, .buttons = 0, .tick = self.sys.ticks() };
                if (self.desk.guiPushEvent(self.process.?.raw, &release_event) >= 0) self.mouse_pending = false;
            }, else => { self.mouse_pending = false; } }
        }
        if (self.state.closeConfirmed) return self.state;
        if (self.process) |*p| {
            if (self.completed == null) {
                if (self.clock() >= self.deadline_ns) self.stop("timeout");
                if (self.stopped != null and self.clock() - self.closing_ns > 2_000_000_000) { _ = p.kill(); }
                switch (p.waitReady(r4os.time_contract.timeoutPoll())) {
                    .ready => |completion| { self.completed = completion; },
                    .would_block, .timed_out => {},
                    .failure => |code| {
                        self.incomplete = true;
                        if (code == abi.program_handle_error_not_found or code == abi.program_handle_error_stale) {
                            self.state.state = "completed";
                            self.state.closeConfirmed = true;
                            self.state.exitEvidenceUnavailable = true;
                            self.state.outputIncomplete = true;
                            return self.state;
                        }
                        self.state.state = "unknown";
                    },
                }
            }
            var count: usize = 0;
            if (self.completed) |completion| {
                if (!self.completion_initialized) {
                    // Completion retains a bounded tail, not an ever-growing
                    // stream. Align its cursor with the last delivered counter.
                    const final_stream = completion.console_state.stdout_bytes +% completion.console_state.stderr_bytes;
                    const delta = final_stream -% self.stream_cursor;
                    if (delta > completion.output_length or completion.console_state.clear_count != self.last_clear) self.incomplete = true;
                    self.output_cursor = completion.output_length - @min(delta, completion.output_length);
                    if (final_stream == 0 and completion.output_length != 0) { self.output_cursor = 0; self.incomplete = true; }
                    self.completion_initialized = true;
                }
                if (self.output_cursor < completion.output_length) {
                    const want = @min(self.output.len, completion.output_length - self.output_cursor);
                    switch (p.completionRead(self.output_cursor, self.output[0..want])) {
                        .bytes => |n| { count = n; self.output_cursor += n; if (n == 0) { self.incomplete = true; self.output_cursor = completion.output_length; } },
                        else => { self.incomplete = true; self.output_cursor = completion.output_length; },
                    }
                }
                self.state.exitCode = completion.exit_code;
                self.state.exitReason = completion.exit_reason;
                self.state.completionSequence = completion.sequence;
                if (self.output_cursor >= completion.output_length) {
                    self.state.state = "completed";
                    self.state.closeConfirmed = true;
                    if (p.owned) { switch (p.reap()) { .exited => {}, else => { self.state.closeConfirmed = false; } } }
                }
            } else {
                switch (p.status()) {
                    .value => |info| { self.state.windowId = info.window_id; },
                    else => { self.state.state = "unknown"; },
                }
                const revision = self.sys.consoleRevision(p.raw);
                var info: abi.ConsoleState = .{};
                const code = self.sys.consoleState(p.raw, &info);
                const got = self.sys.consoleOutput(p.raw, &self.output);
                if (code == 0 and got >= 0 and self.sys.consoleRevision(p.raw) == revision and
                    @as(u32, @intCast(got)) == @min(info.output_len, self.output.len - 1)) {
                    const total = info.stdout_bytes +% info.stderr_bytes;
                    const delta = total -% self.stream_cursor;
                    if (info.clear_count != self.last_clear or delta > @as(u32, @intCast(got))) self.incomplete = true;
                    const fresh = @min(delta, @as(u32, @intCast(got)));
                    const start_at = @as(usize, @intCast(got)) - fresh;
                    std.mem.copyForwards(u8, &self.output, self.output[start_at..@intCast(got)]);
                    count = fresh;
                    self.stream_cursor = total;
                    self.output_cursor = info.output_len + info.output_dropped_bytes;
                    self.last_clear = info.clear_count;
                }
            }
            if (count != 0) {
                const n = std.base64.standard.Encoder.calcSize(count);
                self.state.outputBase64 = std.base64.standard.Encoder.encode(self.encoded[0..n], self.output[0..count]);
            }
            self.state.outputIncomplete = self.incomplete;
            if (!self.console_role and !self.service_owned and self.completed == null) self.windowState();
            if (self.ownsService()) {
                var info: abi.ServiceInfo = .{};
                if (self.sys.serviceStatus(&self.service, &info) == 0) {
                    self.state.serviceState = info.state;
                    self.state.serviceEndpointReady = info.state == abi.service_state_running and (info.flags & abi.service_api_flag_endpoint) != 0;
                }
            }
        }
        return self.state;
    }
};

pub fn serve(app: *r4os.App, instance: []const u8, module_path: []const u8) i32 {
    return @import("transport.zig").serve(app, instance, module_path);
}

pub fn watch(app: *r4os.App, instance: []const u8) i32 {
    const sys = app.system();
    if (instance.len != 36 or sys.monotonicNanoseconds() == null) return 70;
    for (instance) |c| if (!(std.ascii.isHex(c) or c == '-')) return 70;
    var module_buffer: [256]u8 = undefined;
    const module_count = sys.programModulePath(&module_buffer);
    if (module_count <= 0) return 71;
    const module_path = module_buffer[0..@intCast(module_count)];
    const slash = std.mem.lastIndexOfScalar(u8, module_path, 92) orelse return 71;
    const parent = module_path[0..slash];
    var request: [256:0]u8 = .{0} ** 256;
    var response: [256:0]u8 = .{0} ** 256;
    if (!@import("transport.zig").paths(parent, instance, &request, &response)) return 71;
    var controller = Controller{ .sys = sys, .desk = app.desktop() orelse return 70 };
    _ = std.fmt.bufPrintZ(&controller.path, "{s}\\APP.R4X", .{parent}) catch return 71;
    if (sys.envSet("CWD", parent) != 0) return 72;
    defer controller.cleanup();
    const publish = @import("transport.zig").publish;
    var own_handle: abi.ProgramProcessHandle = .{};
    if (sys.programOpenHandle(@intCast(app.raw.instance_id), &own_handle) != 0) return 73;
    var generation: [24]u8 = undefined;
    const generation_text = std.fmt.bufPrint(&generation, "{d}", .{own_handle.generation}) catch return 73;
    if (!publish(sys, &response, instance, 0, true, .{ .ready = true, .daemonInstanceId = own_handle.instance_id,
        .daemonGeneration = generation_text })) return 73;
    var sequence: u32 = 0;
    const born = sys.monotonicNanoseconds().?;
    var heartbeat = born;
    while (true) {
        const current = sys.monotonicNanoseconds() orelse return 73;
        if (current - heartbeat > 15_000_000_000 or current - born > 310_000_000_000 or sys.programShouldClose()) {
            controller.stop("control_lost");
            for (0..350) |_| {
                const state = controller.observe();
                if (state.closeConfirmed) { _ = publish(sys, &response, instance, sequence, true, state); break; }
                sys.sleepTicks(1);
            }
            return 74;
        }
        if (controller.started and controller.completed == null and !controller.state.closeConfirmed) {
            if (current >= controller.deadline_ns) controller.stop("timeout");
            if (controller.stopped != null and current - controller.closing_ns > 2_000_000_000) {
                if (controller.process) |*p| { _ = p.kill(); }
            }
        }
        var line: [4096]u8 = undefined;
        const length = @import("transport.zig").readFile(sys, &request, &line);
        if (length <= 0) { sys.sleepTicks(1); continue; }
        var memory: [24576]u8 = undefined;
        var allocator = std.heap.FixedBufferAllocator.init(&memory);
        const parsed = std.json.parseFromSlice(Request, allocator.allocator(), line[0..@intCast(length)], .{}) catch { sys.sleepTicks(1); continue; };
        const req = parsed.value;
        if (req.version != 1 or !std.mem.eql(u8, req.instance, instance)) return 76;
        if (req.sequence == sequence) { sys.sleepTicks(1); continue; }
        if (req.sequence != sequence + 1) return 76;
        sequence = req.sequence; heartbeat = current;
        if (std.mem.eql(u8, req.operation, "start")) {
            if (!controller.start(req)) { _ = publish(sys, &response, instance, sequence, false, .{ .@"error" = "The owned role could not be started." }); return 77; }
        } else if (std.mem.eql(u8, req.operation, "adopt_desktop")) {
            if (!controller.adoptDesktop(req)) { _ = publish(sys, &response, instance, sequence, false, .{ .@"error" = "The exact Desktop process generation could not be adopted." }); return 77; }
        } else if (std.mem.eql(u8, req.operation, "service_check")) {
            controller.serviceCheck();
        } else if (std.mem.eql(u8, req.operation, "input")) {
            if (!controller.input(req)) { _ = publish(sys, &response, instance, sequence, false, .{ .@"error" = "Input was not accepted for this owned console." }); continue; }
        } else if (std.mem.eql(u8, req.operation, "stop")) {
            controller.stop("user_stop");
        } else if (std.mem.eql(u8, req.operation, "finish")) {
            if (controller.started and !controller.state.closeConfirmed) return 78;
            controller.cleanup(); controller.service_owned = !controller.service_removed;
            _ = publish(sys, &response, instance, sequence, controller.service_removed, .{ .closed = true, .serviceRemoved = controller.service_removed });
            return 0;
        } else if (!std.mem.eql(u8, req.operation, "poll")) return 79;
        const state = controller.observe();
        if (!publish(sys, &response, instance, sequence, true, state)) return 80;
    }
}
