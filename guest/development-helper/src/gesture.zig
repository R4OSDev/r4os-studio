//! Bounded own-client event plans. No physical pointer or desktop capture.
pub const Step = struct {
    phase: enum { down, move, up },
    button: enum { none, left, right } = .none,
    x: i32,
    y: i32,
    atMilliseconds: u32,
};

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
