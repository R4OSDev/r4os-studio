"""Compose frozen global and project sources without native file discovery."""
import hashlib
from store import ProjectFault
from system_prompt import validate_text
from project_agents import NAME, validate


def base(config):
    if config.get('owner', {}).get('type') == 'skill':
        source = config.get('skillManagerPrompt', {})
        text = validate_text(source.get('text'))
        if hashlib.sha256(text.encode()).hexdigest() != source.get('sha256'):
            raise ProjectFault('The saved Skill Manager prompt checksum changed.', 409)
        return ('These are the current R4OS Studio Skill Manager instructions. They replace earlier '
                'Studio author instructions in this conversation.\n\n' + text)
    global_text = validate_text(config['systemPrompt']['text'])
    project = config.get('projectInstructions')
    if 'projectInstructions' not in config:
        # Already admitted legacy runs keep their original instruction source.
        return ('These are the current global R4OS Studio instructions. '
                'They replace any earlier R4OS Studio system prompt.\n\n' + global_text)
    if not isinstance(project, dict) or set(project) != {'path', 'text', 'sha256'} or project['path'] != NAME:
        raise ProjectFault('The saved project instructions snapshot is invalid.', 409)
    text = validate(project['text'])
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != project['sha256']:
        raise ProjectFault('The saved project instructions checksum changed.', 409)
    return ('The following are the current R4OS Studio instruction sources for this run. '
            'They replace all earlier Studio global and project instruction versions in this conversation. '
            'Global instructions take precedence over conflicting project instructions. '
            'Project instructions supplement the global instructions; an empty project source adds no instructions.\n\n'
            'GLOBAL R4OS STUDIO INSTRUCTIONS\n' + global_text +
            '\n\nPROJECT INSTRUCTIONS FROM Workspace/Agents.md\n' + text)


def compose(config):
    text = base(config)
    if 'skillAccess' not in config: return text
    from skill_application import catalog_text
    return text + catalog_text(config['skillAccess'])
