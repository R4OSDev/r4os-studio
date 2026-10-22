import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from gui_startup import adapt, ASSETS


class GuiStartup(unittest.TestCase):
    def test_adapts_copied_starters_and_preserves_other_templates(self):
        for language, name, call, helper in [
            ('Zig', 'main.zig', 'window.beginPaint()', 'studio_gui.zig'),
            ('C', 'main.c', 'r4_window_begin_paint(window, &paint)', 'studio_gui.h'),
        ]:
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); (root / 'src').mkdir(); source = root / 'src' / name
                source.write_text(call)
                project = {'language': language, 'template': 'desktop'}
                self.assertTrue(adapt(root, project))
                self.assertNotIn(call, source.read_text())
                self.assertEqual((root / 'src' / helper).read_bytes(), (ASSETS / helper).read_bytes())
                before = source.read_bytes()
                self.assertFalse(adapt(root, project))
                self.assertEqual(source.read_bytes(), before)
                source.write_text('future SDK starter with its own window setup')
                self.assertFalse(adapt(root, project))
                self.assertEqual(source.read_text(), 'future SDK starter with its own window setup')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(adapt(root, {'language': 'Rust', 'template': 'desktop'}))
            self.assertFalse(adapt(root, {'language': 'Zig', 'template': 'terminal'}))
            self.assertEqual(list(root.iterdir()), [])

    def test_helper_conflict_does_not_rewrite_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'src').mkdir()
            source = root / 'src/main.zig'; source.write_text('window.beginPaint()')
            (root / 'src/studio_gui.zig').write_text('preserve this file')
            with self.assertRaises(FileExistsError):
                adapt(root, {'language': 'Zig', 'template': 'desktop'})
            self.assertEqual(source.read_text(), 'window.beginPaint()')

    @unittest.skipUnless(os.environ.get('STUDIO_GUI_TEST_ZIG'), 'Set STUDIO_GUI_TEST_ZIG to the selected compiler')
    def test_zig_first_frame_real_resize_and_drawing_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); shutil.copyfile(ASSETS / 'studio_gui.zig', root / 'studio_gui.zig')
            (root / 'r4os.zig').write_text('''
pub const Info = struct { client_w: i32, client_h: i32 };
pub const Window = struct {
    value: ?Info = null,
    draw: struct { failure: i32 = 0 } = .{},
    pub fn info(self: *Window) ?Info { return self.value; }
};
pub const app_gui = struct {
    pub const PaintOpen = union(enum) { paint: Info, failure: i32 };
    pub fn beginPaintForSize(draw: anytype, width: i32, height: i32) PaintOpen {
        if (draw.failure < 0) return .{ .failure = draw.failure };
        return .{ .paint = .{ .client_w = width, .client_h = height } };
    }
};
''')
            (root / 'test.zig').write_text('''
const std = @import("std");
const r4os = @import("r4os");
const startup = @import("studio_gui.zig");
test "first paint before size, then real client size and errors" {
    var window: r4os.Window = .{};
    try std.testing.expectEqual(@as(i32, 480), startup.beginPaint(&window).paint.client_w);
    window.value = .{ .client_w = 0, .client_h = 0 };
    try std.testing.expectEqual(@as(i32, 240), startup.beginPaint(&window).paint.client_h);
    window.value = .{ .client_w = 200, .client_h = 100 };
    try std.testing.expectEqualDeep(window.value.?, startup.beginPaint(&window).paint);
    window.value = .{ .client_w = 800, .client_h = 600 };
    try std.testing.expectEqualDeep(window.value.?, startup.beginPaint(&window).paint);
    window.draw.failure = -71;
    try std.testing.expectEqual(@as(i32, -71), startup.beginPaint(&window).failure);
    window.value = null;
    try std.testing.expectEqual(@as(i32, -71), startup.beginPaint(&window).failure);
}
''')
            subprocess.run([os.environ['STUDIO_GUI_TEST_ZIG'], 'test', '--dep', 'r4os',
                            '-Mroot=' + str(root / 'test.zig'), '-Mr4os=' + str(root / 'r4os.zig'),
                            '--cache-dir', str(root / 'cache')], check=True, capture_output=True, timeout=60)

    @unittest.skipUnless(shutil.which('cc'), 'A host C compiler is required')
    def test_c_first_frame_real_resize_and_drawing_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'r4os').mkdir()
            shutil.copyfile(ASSETS / 'studio_gui.h', root / 'studio_gui.h')
            (root / 'r4os/r4os.h').write_text('''
#ifndef FAKE_R4OS_H
#define FAKE_R4OS_H
#include <stdint.h>
typedef struct { int32_t client_w, client_h; } R4GuiWindowInfo;
typedef struct { int desktop, drawing; } R4App;
typedef struct { R4App *app; } R4Window;
typedef struct { R4Window *window; R4GuiWindowInfo info; uint8_t active, transactional; } R4PaintContext;
static R4GuiWindowInfo size;
static int frame_failure, info_failure;
static int r4desk_gui_window_info(int *desktop, R4GuiWindowInfo *out) { (void)desktop; *out=size; return info_failure; }
static int r4draw_supports_gui_frame_contract(int *drawing) { (void)drawing; return 1; }
static int r4draw_gui_frame_begin(int *drawing) { (void)drawing; return frame_failure; }
static int r4_window_begin_paint(R4Window *w, R4PaintContext *out) {
    *out=(R4PaintContext){0}; out->window=w; out->info=size;
    if (frame_failure<0) return 0; out->active=1; return 1;
}
#endif
''')
            (root / 'test.c').write_text('''
#include "studio_gui.h"
#include <assert.h>
int main(void) {
    R4App app={0}; R4Window window={&app}; R4PaintContext paint;
    assert(studio_begin_paint(&window,&paint));
    assert(paint.active && paint.info.client_w==480 && paint.info.client_h==240);
    size=(R4GuiWindowInfo){200,100};
    assert(studio_begin_paint(&window,&paint));
    assert(paint.info.client_w==200 && paint.info.client_h==100);
    frame_failure=-71;
    assert(!studio_begin_paint(&window,&paint)); assert(!paint.active);
    size=(R4GuiWindowInfo){0,0};
    assert(!studio_begin_paint(&window,&paint)); assert(!paint.active);
    frame_failure=0; info_failure=-1;
    assert(studio_begin_paint(&window,&paint)); assert(paint.info.client_w==480);
    assert(!studio_begin_paint(0,&paint)); assert(!studio_begin_paint(&window,0));
    return 0;
}
''')
            subprocess.run(['cc', '-std=c11', '-I', temp, str(root / 'test.c'), '-o', str(root / 'test')],
                           check=True, capture_output=True, timeout=30)
            subprocess.run([str(root / 'test')], check=True, capture_output=True, timeout=10)


if __name__ == '__main__': unittest.main()
