"""Reject retired desktop effects; preserve all original records and guest files."""
from contracts import DevelopmentFault


def request(value):
    if isinstance(value, dict) and any(key in value for key in ('desktopShortcut', 'desktopLink')):
        raise DevelopmentFault('Use the declared deployment or run arguments. For an explicitly requested guest shortcut, use the permitted project VM SSH tool.', 410, reason_code='desktop_automation_removed')


def job(value):
    if value.get('desktopShortcutRequested') or value.get('desktopLinkRequested'):
        raise DevelopmentFault('This job is read-only. Inspect its stored receipts through the development job reader.', 410, reason_code='desktop_automation_removed')
