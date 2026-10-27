"""Bounded codepoint events; names match r4os.gui.Key in the pinned SDK."""
from contracts import DevelopmentFault

KEYS = {'Enter': 13, 'Tab': 9, 'Escape': 27, 'Space': 32, 'Backspace': 8, 'Delete': 127,
    'ArrowUp': 128, 'ArrowDown': 129, 'Shift+Tab': 132, 'ArrowLeft': 136, 'ArrowRight': 137,
    'Home': 138, 'End': 139, 'PageUp': 141, 'PageDown': 142}
LEGACY_KEYS = ('Enter', 'Tab', 'Escape', 'Space')


def key(value):
    if isinstance(value, str):
        if value in KEYS: return KEYS[value]
        if len(value) == 1 and 32 <= ord(value) <= 126: return ord(value)
    raise DevelopmentFault('Use one printable ASCII character or a supported navigation key; use GUI text for Unicode.', 400)


def text(value):
    try:
        valid = (isinstance(value, str) and 0 < len(value) <= 64 and len(value.encode('utf-8')) <= 256
            and not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value))
    except UnicodeError: valid = False
    if not valid: raise DevelopmentFault('GUI text is limited to 64 Unicode characters and 256 UTF-8 bytes, without control characters. Send Enter or Tab separately.', 400)
    return value
