/* Studio GUI starter: draw the first frame before Desktop publishes its size. */
#ifndef STUDIO_GUI_H
#define STUDIO_GUI_H
#include <r4os/r4os.h>

static inline int studio_begin_paint(R4Window *window, R4PaintContext *out)
{
    if (window == 0 || out == 0 || window->app == 0) return 0;
    R4GuiWindowInfo info = {0};
    if (r4desk_gui_window_info(&window->app->desktop, &info) >= 0 &&
        info.client_w > 0 && info.client_h > 0) {
        return r4_window_begin_paint(window, out);
    }
    /* R4PaintContext and its frame lifecycle are the SDK's public C facade. */
    *out = (R4PaintContext){0};
    out->window = window;
    out->info.client_w = 480;
    out->info.client_h = 240;
    out->transactional = (uint8_t)r4draw_supports_gui_frame_contract(&window->app->drawing);
    if (out->transactional && r4draw_gui_frame_begin(&window->app->drawing) < 0) return 0;
    out->active = 1u;
    return 1;
}
#endif
