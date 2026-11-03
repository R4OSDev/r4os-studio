"""Reject retired desktop effects; preserve all original records and guest files."""
from contracts import DevelopmentFault


def request(value):
    if isinstance(value, dict) and any(key in value for key in ('desktopShortcut', 'desktopLink')):
        raise DevelopmentFault('Studio desktop publication and managed link activation were removed. Use a normal deployment/run, or the project VM SSH tool for an explicitly requested guest shortcut.', 410, reason_code='desktop_automation_removed')


def job(value):
    if value.get('desktopShortcutRequested') or value.get('desktopLinkRequested'):
        raise DevelopmentFault('This historical desktop automation job is read-only in current Studio. Its original receipts and guest files are retained; no publication or link activation was repeated.', 410, reason_code='desktop_automation_removed')
