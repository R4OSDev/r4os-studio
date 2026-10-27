"""Add bound release guidance without rewriting any saved instruction source."""
from pathlib import Path
from roadmap_access import availability


def compose(config):
    if config.get('owner', {}).get('type') != 'project': return ''
    if config.get('roadmapEnabled') is not True:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: Roadmap tools are disabled for this run. '
                'Earlier roadmap content remains in the native history but grants no access. '
                'Do not bypass the frozen setting through files, shell, external URLs or another session.')
    if not availability(config.get('engine', {}).get('profile'))['available']:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: The Roadmap preference is on, but this conversation '
                'keeps its original native tool profile without Roadmap tools. New session required. '
                'Its existing thread and history must be preserved. Do not claim access or bypass this '
                'capability with files, shell or an external roadmap service.')
    source = Path(__file__).resolve().parents[2] / 'shared/project-roadmap-instructions.txt'
    return ('\n\nThe following bound Roadmap contract applies to this run and supersedes conflicting '
            'earlier roadmap instructions. It changes no saved prompt source or tool permission.\n\n'
            + source.read_text(encoding='utf-8'))
