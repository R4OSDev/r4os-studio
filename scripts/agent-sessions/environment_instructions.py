"""Project-bound guidance; no native capabilities are inferred from SDK numbers."""
import json


def compose(project):
    from host_linker import qualify
    pins = project.get('pins', {})
    context = {'projectRevision': project.get('revision'), 'language': project.get('language'),
               'role': project.get('template'), 'hostCLinker': qualify()}
    for name in ('sdk', 'contract', 'zig', 'rust'):
        value = pins.get(name)
        if isinstance(value, dict):
            context[name] = {key: value[key] for key in ('version', 'revision') if key in value}
    return ('\n\nSTUDIO PROJECT ENVIRONMENT: Current project metadata at worker startup: '
        + json.dumps(context, ensure_ascii=False, sort_keys=True) + '. '
        'This describes configured host build inputs, not the capabilities of a running guest or an older deployed artifact. '
        'Use the original build/deployment pins and authenticated guest evidence for that target; do not change pins to work around missing APIs. '
        'Studio currently has no qualified own-window resize/minimize/restore adapter. Legacy WINSVC record operations and '
        'gui_set_window_info are not proof of applied Desktop geometry. The qualified SDK0.64.92/Contract0.64.45 WindowMode '
        'request describes decorated/fullscreen mode only; do not invent size, minimize or restore fields, global input or local ABI numbers. '
        'Keep requested window-action and outside-client drag checks open until a supported native contract and actual effects are established. '
        'For C GUI work, distinguish the higher app_gui.h message facade from technical generated raw focus/font enums and native window flags; '
        'WindowService flags are not interchangeable with GuiWindowFlag. Inspect the selected SDK/Contract sources before using an enum. '
        'Long staging names failed on the observed Full0.87.14 Exchange provider while checked short basenames worked; '
        'that observation is not an 8.3 restriction on every R4OS volume. Do not rename unrelated application files or infer a filesystem defect. '
        'Host Rust app compilation does not establish a native Rust compiler in the guest. In SDK0.64.92/51ed03d813d9baeab630746f1d1bbc46c2d2a1e6 '
        'and Contract0.64.45/db155842d346a8aae0aadea73288105140c95af6, native compilers and HTTP POST/SSE streaming, '
        'TCP deadlines/PeerClosed semantics must be qualified in the actual language API. A Studio model provider cannot add guest networking APIs. '
        'Missing glyphs need localization to application/font/rendering; do not silently substitute text or claim a Studio encoding defect. '
        'For host-only Rust tests, cc in the tool terminal resolves to the qualified existing public host driver; '
        'an unavailable driver produces a specific Host C linker diagnostic. This is separate from pinned native R4X build/link tooling; '
        'do not change project pins, test scripts or global compiler defaults to repair a host linker. '
        'The detailed pinned qualification is documented in the Studio installation as R4OS-Environment.md; '
        'that Studio documentation is separate from the app workspace.')
