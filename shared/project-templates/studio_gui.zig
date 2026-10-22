// Studio GUI starter: the Desktop may publish the client size after app entry.
const r4os = @import("r4os");

pub fn beginPaint(window: *r4os.Window) r4os.app_gui.PaintOpen {
    const info = window.info();
    if (info) |value| {
        if (value.client_w > 0 and value.client_h > 0) {
            return r4os.app_gui.beginPaintForSize(&window.draw, value.client_w, value.client_h);
        }
    }
    // Bootstrap drawing without inventing or publishing a Desktop window size.
    // Subsequent paints use the real client size, including smaller windows.
    return r4os.app_gui.beginPaintForSize(&window.draw, 480, 240);
}
