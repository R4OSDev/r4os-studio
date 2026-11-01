//! Broker leases outlive this reader. The host persists each token before the
//! next mutation; this adapter never launches or reaps the observed process.
const std = @import("std");
const r4os = @import("r4os");
const a = r4os.abi;
pub const Token = a.DesktopEvidenceToken;

pub fn decode(text: []const u8) ?Token {
    var token: Token = .{};
    const bytes = std.mem.asBytes(&token);
    if ((std.base64.standard.Decoder.calcSizeForSlice(text) catch return null) != bytes.len) return null;
    std.base64.standard.Decoder.decode(bytes, text) catch return null;
    if (token.version != 1 or token.size != @sizeOf(Token) or token.broker.instance_id == 0 or
        token.broker.generation == 0 or token.request.instance_id == 0 or token.request.generation == 0 or
        token.epoch[0] | token.epoch[1] | token.epoch[2] == 0 or token.intent[0] | token.intent[1] | token.intent[2] == 0) return null;
    return token;
}

pub fn call(sys: r4os.r4sys.Context, op: []const u8, token: Token, offset: u32, out: []u8) r4os.desktop_evidence.Call {
    const client = r4os.desktop_evidence.Client{ .sys = sys };
    if (std.mem.eql(u8, op, "status")) return client.status(token);
    if (std.mem.eql(u8, op, "read")) return client.read(token, offset, out);
    if (std.mem.eql(u8, op, "reserve")) return client.reserve(token);
    if (std.mem.eql(u8, op, "offer")) return client.offer(token);
    if (std.mem.eql(u8, op, "ack")) return client.acknowledge(token);
    if (std.mem.eql(u8, op, "release")) return client.release(token);
    return .{ .failure = a.desktop_evidence_result_invalid };
}

pub fn respond(sys: r4os.r4sys.Context, path: [*:0]const u8, instance: []const u8, sequence: u32,
    operation: []const u8, text: []const u8, offset: u32) bool {
    const publish = @import("transport.zig").publish;
    const token = decode(text) orelse return publish(sys, path, instance, sequence, false, .{ .@"error" = "Invalid original evidence token." });
    var bytes: [a.desktop_evidence_max_output_chunk]u8 = undefined;
    const result = call(sys, operation, token, offset, &bytes);
    if (result == .failure) return publish(sys, path, instance, sequence, true, .{ .transportError = result.failure });
    const reply = result.reply;
    var encoded_token: [172]u8 = undefined;
    var encoded_data: [5080]u8 = undefined;
    var generation: [24]u8 = undefined;
    var serial: [24]u8 = undefined;
    var completion: [24]u8 = undefined;
    return publish(sys, path, instance, sequence, true, .{
        .token = std.base64.standard.Encoder.encode(&encoded_token, std.mem.asBytes(&reply.token)),
        .result = reply.result, .phase = reply.phase, .rawResult = reply.raw_result,
        .serial = std.fmt.bufPrint(&serial, "{d}", .{reply.token.serial}) catch return false,
        .instanceId = reply.token.process.instance_id,
        .generation = std.fmt.bufPrint(&generation, "{d}", .{reply.token.process.generation}) catch return false,
        .completionSequence = std.fmt.bufPrint(&completion, "{d}", .{reply.completion.sequence}) catch return false,
        .exitCode = reply.completion.exit_code, .exitReason = reply.completion.exit_reason,
        .outputLength = reply.completion.output_length, .outputFlags = reply.completion.flags,
        .outputComplete = reply.completion.flags & a.program_completion_flag_output_available != 0 and
            reply.completion.flags & (a.program_completion_flag_output_incomplete | a.program_completion_flag_output_truncated) == 0,
        .outputBase64 = std.base64.standard.Encoder.encode(encoded_data[0..std.base64.standard.Encoder.calcSize(reply.data_bytes)], bytes[0..reply.data_bytes]),
    });
}

/// A fresh reader of a saved token, using the deployment's fixed request file.
/// No reserve/offer/ack is admitted here; recovery cannot create a reference.
pub fn recover(sys: r4os.r4sys.Context, instance: []const u8, module: []const u8) i32 {
    const slash = std.mem.lastIndexOfScalar(u8, module, '\\') orelse return 95;
    var input: [256:0]u8 = .{0} ** 256;
    var output: [256:0]u8 = .{0} ** 256;
    const short = instance[0..7];
    _ = std.fmt.bufPrintZ(&input, "{s}\\E{s}.JSN", .{module[0..slash], short}) catch return 95;
    _ = std.fmt.bufPrintZ(&output, "{s}\\V{s}.JSN", .{module[0..slash], short}) catch return 95;
    var bytes: [1024]u8 = undefined;
    const n = @import("transport.zig").readFile(sys, &input, &bytes);
    if (n <= 0) return 95;
    var memory: [4096]u8 = undefined;
    var allocator = std.heap.FixedBufferAllocator.init(&memory);
    const Request = struct { instance: []const u8, operation: []const u8, token: []const u8, offset: u32 = 0 };
    const parsed = std.json.parseFromSlice(Request, allocator.allocator(), bytes[0..@intCast(n)], .{}) catch return 95;
    const req = parsed.value;
    if (!std.mem.eql(u8, req.instance, instance) or
        !(std.mem.eql(u8, req.operation, "status") or std.mem.eql(u8, req.operation, "read") or std.mem.eql(u8, req.operation, "release"))) return 95;
    if (!respond(sys, &output, instance, 0, req.operation, req.token, req.offset)) return 95;
    var frame: [12288]u8 = undefined;
    const count = @import("transport.zig").readFile(sys, &output, &frame);
    if (count <= 0) return 95;
    sys.write(frame[0..@intCast(count)]); sys.println("");
    return 0;
}
