//! One project-owned desktop link. No caller-selected paths, shell, or app launch.
const std = @import("std");
const r4os = @import("r4os");
const transport = @import("transport.zig");
const Context = r4os.r4sys.Context;
const Request = struct {
    version: u32,
    requestId: []const u8,
    projectId: []const u8,
    deploymentId: []const u8,
    title: []const u8,
    previous: ?[]const u8,
};
const Owner = struct { interface: []const u8, schema: u32, projectId: []const u8, deploymentId: []const u8, exchangeGeneration: []const u8 };

fn uuid(value: []const u8) bool {
    if (value.len != 36) return false;
    for (value, 0..) |c, i| {
        if (i == 8 or i == 13 or i == 18 or i == 23) {
            if (c != '-') return false;
        } else if (!std.ascii.isHex(c)) return false;
    }
    return true;
}

fn checksum(data: []const u8) u32 {
    var sum: u32 = 2166136261;
    for (data) |c| { sum ^= c; sum *%= 16777619; }
    return sum;
}

fn read(sys: Context, path: [*:0]const u8, buffer: []u8) ?[]const u8 {
    const n = transport.readFile(sys, path, buffer);
    return if (n >= 0) buffer[0..@intCast(n)] else null;
}

fn absent(sys: Context, path: [*:0]const u8) bool {
    var info: r4os.abi.FileInfo = .{};
    return sys.fileInfoRaw(path, &info) == 0;
}

fn create(sys: Context, path: [*:0]const u8, data: []const u8) bool {
    if (sys.fileStreamBegin(path, r4os.abi.file_stream_open_create) != 0) return false;
    if (sys.fileStreamWrite(path, 0, data, 0) != @as(i32, @intCast(data.len))) {
        _ = sys.fileStreamAbort(path); return false;
    }
    if (sys.fileStreamFinish(path, data.len, 0) != 0) return false;
    return true;
}

pub fn available(sys: Context) bool {
    return sys.hasFn("file_update_atomic_checked") and sys.hasFn("file_delete_if_match") and
        sys.hasFn("file_stream_begin") and sys.hasFn("file_stream_write") and sys.hasFn("file_stream_finish") and sys.hasFn("file_stream_abort");
}

const Reporter = struct {
    sys: Context,
    allocator: std.mem.Allocator,
    request: Request,
    path: [*:0]const u8,
    link: []const u8,
    target: []const u8,
    content: []const u8,
    intent_created: bool = false,
    link_replaced: bool = false,
    readback_verified: bool = false,
    cleanup_confirmed: bool = false,

    fn fail(self: *Reporter, code: i32, phase: []const u8, native_result: ?i32) i32 {
        const value = .{
            .version = @as(u32, 1), .requestId = self.request.requestId,
            .projectId = self.request.projectId, .deploymentId = self.request.deploymentId,
            .linkPath = self.link, .target = self.target, .content = self.content,
            .success = false, .phase = phase, .exitCode = code, .nativeResult = native_result,
            .mutationMayHaveOccurred = self.intent_created, .linkReplaced = self.link_replaced,
            .readbackVerified = self.readback_verified, .cleanupConfirmed = self.cleanup_confirmed,
            .applicationStarted = false,
        };
        const output = std.json.Stringify.valueAlloc(self.allocator, value, .{}) catch return code;
        if (self.intent_created) _ = create(self.sys, self.path, output);
        self.sys.write(output);
        self.sys.println("");
        return code;
    }
};

pub fn run(sys: Context, instance: []const u8, module: []const u8) i32 {
    if (!available(sys) or !uuid(instance)) return 100;
    const slash = std.mem.lastIndexOfScalar(u8, module, '\\') orelse return 101;
    const parent = module[0..slash];
    // The public deployment owns exactly /<drive>/Build/Pxxxxxxx/Dxxxxxxx.
    if (parent.len != 26 or parent[1] != ':' or !std.mem.eql(u8, parent[2..10], "\\Build\\P") or parent[17] != '\\' or parent[18] != 'D') return 101;
    for (parent[10..17]) |c| if (!std.ascii.isHex(c)) return 101;
    for (parent[19..]) |c| if (!std.ascii.isHex(c)) return 101;
    var request_path: [256:0]u8 = .{0} ** 256;
    var response_path: [256:0]u8 = .{0} ** 256;
    var intent_path: [256:0]u8 = .{0} ** 256;
    var error_path: [256:0]u8 = .{0} ** 256;
    var owner_path: [256:0]u8 = .{0} ** 256;
    _ = std.fmt.bufPrintZ(&request_path, "{s}\\DSKIN.JSN", .{parent}) catch return 102;
    _ = std.fmt.bufPrintZ(&response_path, "{s}\\DSKOUT.JSN", .{parent}) catch return 102;
    _ = std.fmt.bufPrintZ(&intent_path, "{s}\\DSKINT.JSN", .{parent}) catch return 102;
    _ = std.fmt.bufPrintZ(&error_path, "{s}\\DSKERR.JSN", .{parent}) catch return 102;
    _ = std.fmt.bufPrintZ(&owner_path, "{s}\\DEPLOY.JSN", .{parent}) catch return 102;
    var frame: [2048]u8 = undefined;
    var owner_frame: [2048]u8 = undefined;
    var memory: [16384]u8 = undefined;
    var allocator = std.heap.FixedBufferAllocator.init(&memory);
    const bytes = read(sys, &request_path, &frame) orelse return 103;
    const parsed = std.json.parseFromSlice(Request, allocator.allocator(), bytes, .{}) catch return 103;
    const request = parsed.value;
    if (request.version != 1 or !std.mem.eql(u8, request.requestId, instance) or !uuid(request.projectId) or !uuid(request.deploymentId)) return 103;
    const owner_bytes = read(sys, &owner_path, &owner_frame) orelse return 104;
    const owner = (std.json.parseFromSlice(Owner, allocator.allocator(), owner_bytes, .{}) catch return 104).value;
    if (owner.schema != 1 or !std.mem.eql(u8, owner.interface, "r4os-studio-deployment-owner") or
        !std.mem.eql(u8, owner.projectId, request.projectId) or !std.mem.eql(u8, owner.deploymentId, request.deploymentId)) return 104;
    if (request.title.len == 0 or request.title.len > 64) return 105;
    for (request.title) |c| if (!(std.ascii.isAlphanumeric(c) or std.mem.indexOfScalar(u8, " ._()-", c) != null)) return 105;
    if (request.previous) |old| { if (old.len > 1024) return 105; }
    const hash = std.crypto.hash.sha2.Sha256.hash;
    var project_hash: [32]u8 = undefined;
    hash(request.projectId, &project_hash, .{});
    var hex: [64]u8 = undefined;
    const digits = "0123456789ABCDEF";
    for (project_hash, 0..) |c, i| { hex[i * 2] = digits[c >> 4]; hex[i * 2 + 1] = digits[c & 15]; }
    if (!std.ascii.eqlIgnoreCase(parent[10..17], hex[0..7]) or !std.ascii.eqlIgnoreCase(parent[19..26], request.deploymentId[0..7])) return 104;
    var target: [128:0]u8 = .{0} ** 128;
    var link: [128:0]u8 = .{0} ** 128;
    var stage: [128:0]u8 = .{0} ** 128;
    var backup: [128:0]u8 = .{0} ** 128;
    var link_remote: [128]u8 = undefined;
    const target_text = std.fmt.bufPrintZ(&target, "{s}\\APP.R4X", .{parent}) catch return 106;
    _ = std.fmt.bufPrintZ(&link, "C:\\R4OS\\DESKTOP\\S{s}.LNK", .{hex[0..7]}) catch return 106;
    _ = std.fmt.bufPrintZ(&stage, "C:\\R4OS\\DESKTOP\\S{s}.TMP", .{hex[0..7]}) catch return 106;
    _ = std.fmt.bufPrintZ(&backup, "C:\\R4OS\\DESKTOP\\S{s}.BAK", .{hex[0..7]}) catch return 106;
    const remote = std.fmt.bufPrint(&link_remote, "/C/R4OS/DESKTOP/S{s}.LNK", .{hex[0..7]}) catch return 106;
    var data_buffer: [1024]u8 = undefined;
    const data = std.fmt.bufPrint(&data_buffer, "R4S_FORMAT=1\nSCHEMA=R4LNK\nTARGET={s}\nTITLE={s}\nPOLICY=gui\nICON=INTERNAL\n", .{target_text, request.title}) catch return 106;
    var reporter = Reporter{ .sys = sys, .allocator = allocator.allocator(), .request = request,
        .path = &error_path, .link = remote, .target = target_text, .content = data };
    var check_buffer: [1024]u8 = undefined;
    if (request.previous) |old| {
        const existing = read(sys, &link, &check_buffer) orelse return reporter.fail(107, "previous_link_read", null);
        if (!std.mem.eql(u8, existing, old)) return reporter.fail(107, "previous_link_compare", null);
    } else if (!absent(sys, &link)) return reporter.fail(107, "unexpected_link", null);
    if (!absent(sys, &stage) or !absent(sys, &backup) or !absent(sys, &intent_path) or !absent(sys, &response_path) or !absent(sys, &error_path)) return reporter.fail(108, "existing_stage_or_receipt", null);
    // This create-only marker prevents repeating a partially completed request.
    if (!create(sys, &intent_path, bytes)) return reporter.fail(109, "intent_create", null);
    reporter.intent_created = true;
    if (!create(sys, &stage, data)) return reporter.fail(110, "stage_create", null);
    var flags = r4os.r4sys.file_update_atomic_checked_flag_forward;
    if (request.previous != null) flags |= r4os.r4sys.file_update_atomic_checked_flag_target_existed | r4os.r4sys.file_update_atomic_checked_flag_old_known;
    const old = request.previous orelse "";
    const rc = sys.fileUpdateAtomicChecked(&link, &stage, &backup, data.len, checksum(data), old.len, checksum(old), flags);
    if (rc != r4os.r4sys.file_update_atomic_checked_result_ok) return reporter.fail(111, "atomic_replace", rc);
    reporter.link_replaced = true;
    const actual = read(sys, &link, &check_buffer) orelse return reporter.fail(112, "link_readback", null);
    if (!std.mem.eql(u8, data, actual)) return reporter.fail(112, "link_compare", null);
    reporter.readback_verified = true;
    var backup_delete_result: ?i32 = null;
    if (request.previous) |_| {
        const prior = read(sys, &backup, &check_buffer) orelse return reporter.fail(113, "backup_readback", null);
        if (!std.mem.eql(u8, prior, old)) return reporter.fail(113, "backup_compare", null);
        const deleted = sys.fileDeleteIfMatch(&backup, old.len, checksum(old));
        backup_delete_result = deleted;
        switch (deleted) {
            r4os.r4sys.file_delete_if_match_result_deleted,
            r4os.r4sys.file_delete_if_match_result_not_found => {},
            else => return reporter.fail(113, "backup_delete", deleted),
        }
    }
    if (!absent(sys, &stage)) return reporter.fail(113, "stage_cleanup", null);
    if (!absent(sys, &backup)) return reporter.fail(113, "backup_cleanup", null);
    const final = read(sys, &link, &check_buffer) orelse return reporter.fail(112, "final_link_readback", null);
    if (!std.mem.eql(u8, data, final)) return reporter.fail(112, "final_link_compare", null);
    reporter.cleanup_confirmed = true;
    const response = .{ .version = @as(u32, 1), .requestId = instance, .projectId = request.projectId,
        .deploymentId = request.deploymentId, .linkPath = remote, .target = target_text, .content = data,
        .success = true, .readbackVerified = true, .cleanupConfirmed = true,
        .applicationStarted = false, .atomicResult = rc, .backupDeleteResult = backup_delete_result };
    const output = std.json.Stringify.valueAlloc(allocator.allocator(), response, .{}) catch return reporter.fail(114, "response_encode", null);
    if (!create(sys, &response_path, output)) return reporter.fail(114, "response_create", null);
    sys.write(output); sys.println("");
    return 0;
}
