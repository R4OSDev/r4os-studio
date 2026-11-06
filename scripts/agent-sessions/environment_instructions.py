"""Project-bound guidance; no native capabilities are inferred from SDK numbers."""
import json


def compose(project, config=None):
    from host_linker import qualify
    pins = project.get('pins', {})
    context = {'projectRevision': project.get('revision'), 'language': project.get('language'),
               'role': project.get('template'), 'hostCLinker': qualify()}
    for name in ('sdk', 'contract', 'zig', 'rust'):
        value = pins.get(name)
        if isinstance(value, dict):
            context[name] = {key: value[key] for key in ('version', 'revision') if key in value}
    from tool_catalog import specifications
    config=config or {};permissions=config.get('permissions',{})
    context['ownWindowControl']={'registered':'studio_control_app_window' in {item['name'] for item in specifications(config)},
        'permittedByFrozenRights':all(permissions.get('studio.'+key) is True for key in ('control_app_window','run_project')),
        'guestAndDeploymentVerified':False}
    return ('\n\nSTUDIO PROJECT ENVIRONMENT: Current project metadata at worker startup: '
        + json.dumps(context, ensure_ascii=False, sort_keys=True) + '. '
        'This describes configured host build inputs, not the capabilities of a running guest or an older deployed artifact. '
        'Use the original build/deployment pins and authenticated guest evidence for that target; do not change pins to work around missing APIs. '
        'Current Studio registers studio_control_app_window for its owned application. Registration and frozen permission do not establish guest readiness. '
        'Control requires a requested windowControl execution, a verified compatible deployment/helper/native guest contract and its current owned process/window binding. '
        'Use the declared resize/minimize/restore operations only when those receipts and permissions allow them; confirm the actual effect. '
        'Legacy WINSVC records or gui_set_window_info alone do not prove applied geometry. Do not invent ABI fields, global input or native capabilities from SDK/version numbers. '
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
