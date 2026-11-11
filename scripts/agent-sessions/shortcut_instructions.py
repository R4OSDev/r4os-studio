"""One current SSH guide in project instructions; original prompt sources stay intact."""
from pathlib import Path

GUIDE = (Path(__file__).resolve().parents[2] / 'shared/project-vm-shortcuts.txt').read_text().strip()


def compose(config, text, source=''):
    if config.get('owner', {}).get('type') != 'project': return text
    tools = (config.get('toolCatalog') or {}).get('tools', [])
    enabled = (config.get('permissions', {}).get('studio.run_vm_command') is True
        and 'studio_run_vm_command' in tools)
    if not enabled or GUIDE in source or GUIDE in text: return text
    return text + '\n\n' + GUIDE
