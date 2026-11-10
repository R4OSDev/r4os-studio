"""One current SSH guide in project instructions; original prompt sources stay intact."""
from pathlib import Path

GUIDE = (Path(__file__).resolve().parents[2] / 'shared/project-vm-shortcuts.txt').read_text().strip()
RETIREMENT = ('CURRENT STUDIO DESKTOP CONTRACT (0.9.27): Studio desktop publication/ownership and managed link '
    'activation were removed. Earlier Studio automation or blanket shell-edit instructions are obsolete. '
    'Original guest links and receipts remain historical. The project VM SSH tool is unavailable in this '
    'run\'s declared tools/permissions; no shortcut-writing capability is claimed.')


def compose(config, text, source=''):
    if config.get('owner', {}).get('type') != 'project': return text
    tools = (config.get('toolCatalog') or {}).get('tools', [])
    enabled = (config.get('permissions', {}).get('studio.run_vm_command') is True
        and 'studio_run_vm_command' in tools)
    guide = GUIDE if enabled else RETIREMENT
    # The source remains verbatim, including any bundled guide. Append a current
    # contract only when missing; disabled tools still receive retirement guidance.
    if guide in source or guide in text: return text
    return text + '\n\n' + guide
