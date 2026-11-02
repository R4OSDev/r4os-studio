//! Normal semantic key/codepoint plans. No held keys, modifiers or clipboard.
const r4os = @import("r4os");
pub const Step = struct {
    kind: enum { key, codepoint },
    value: u32,
    atMilliseconds: u32,
};

pub fn normalKey(value: u32) bool {
    return switch (value) {
        ' '...'~', r4os.gui.Key.backspace, r4os.gui.Key.tab, r4os.gui.Key.enter, r4os.gui.Key.escape,
        r4os.gui.Key.delete, r4os.gui.Key.up, r4os.gui.Key.down, r4os.gui.Key.shift_tab,
        r4os.gui.Key.left, r4os.gui.Key.right, r4os.gui.Key.home, r4os.gui.Key.end,
        r4os.gui.Key.page_up, r4os.gui.Key.page_down => true,
        else => false,
    };
}

pub fn valid(steps: []const Step) bool {
    if (steps.len == 0 or steps.len > 32) return false;
    var previous: u32 = 0;
    for (steps) |step| {
        if (step.atMilliseconds < previous or step.atMilliseconds > 2000) return false;
        previous = step.atMilliseconds;
        switch (step.kind) {
            .key => if (!normalKey(step.value)) return false,
            .codepoint => if (step.value < 32 or step.value > 0x10ffff or
                (step.value >= 127 and step.value < 160) or
                (step.value >= 0xd800 and step.value <= 0xdfff)) return false,
        }
    }
    return true;
}
