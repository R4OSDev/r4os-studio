"""Adapt copied GUI starters; installed SDK files and project pins stay intact."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / 'shared/project-templates'


def adapt(directory, project):
    if project['template'] not in ('desktop', 'subsystem'):
        return False
    variants = {
        'Zig': ('main.zig', 'window.beginPaint()', 'studio_gui.beginPaint(window)',
                'const studio_gui = @import("studio_gui.zig");\n', 'studio_gui.zig'),
        'C': ('main.c', 'r4_window_begin_paint(window, &paint)', 'studio_begin_paint(window, &paint)',
              '#include "studio_gui.h"\n', 'studio_gui.h'),
    }
    if project['language'] not in variants:
        return False
    name, original, replacement, include, asset = variants[project['language']]
    source = directory / 'src' / name
    if source.is_symlink():
        raise ValueError('Unexpected GUI starter source link.')
    if not source.is_file():
        return False
    text = source.read_text(encoding='utf-8-sig')
    # This only runs on freshly generated SDK starters. Templates that use a
    # different GUI path remain unchanged, including the Rust drawing facade.
    if original not in text:
        return False
    helper = source.with_name(asset)
    with helper.open('x', encoding='utf-8') as stream:
        stream.write((ASSETS / asset).read_text())
    source.write_text(include + text.replace(original, replacement), encoding='utf-8')
    return True
