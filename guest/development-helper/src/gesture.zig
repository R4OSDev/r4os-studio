//! Bounded own-client event plans. No physical pointer or desktop capture.
pub const Step = struct {
    phase: enum { down, move, up },
    button: enum { none, left, right } = .none,
    x: i32,
    y: i32,
    atMilliseconds: u32,
};

pub const Interrupt = struct {
    action: enum { escape, resize, minimize },
    atMilliseconds: u32,
    nativeRequest: []const u8 = "",
};

pub fn validInterrupt(value: Interrupt, steps: []const Step) bool {
    if (steps.len < 2 or steps[steps.len - 1].phase != .up or
        value.atMilliseconds < steps[steps.len - 2].atMilliseconds or
        value.atMilliseconds > steps[steps.len - 1].atMilliseconds) return false;
    return switch (value.action) {
        .escape => value.nativeRequest.len == 0,
        .resize, .minimize => value.atMilliseconds <= 1000 and value.nativeRequest.len > 0 and value.nativeRequest.len <= 512,
    };
}

pub fn buttonMask(step: Step) u32 {
    return switch (step.button) { .none => 0, .left => 1, .right => 2 };
}

pub fn valid(steps: []const Step, width: i32, height: i32) bool {
    if (steps.len == 0 or steps.len > 32) return false;
    var previous: u32 = 0;
    var held: u32 = 0;
    for (steps) |step| {
        if (step.atMilliseconds < previous or step.atMilliseconds > 2000 or
            step.x < 0 or step.y < 0 or step.x >= width or step.y >= height) return false;
        previous = step.atMilliseconds;
        const mask = buttonMask(step);
        switch (step.phase) {
            .move => { if (mask != 0) return false; },
            .down => { if (held != 0 or mask == 0) return false; held = mask; },
            .up => { if (held == 0 or held != mask) return false; held = 0; },
        }
    }
    return held == 0;
}
