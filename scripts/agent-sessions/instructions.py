"""Compose frozen global and project sources without native file discovery."""
import hashlib
from store import ProjectFault
from system_prompt import validate_text
from project_agents import NAME, validate

TERMINAL_TIMING = (
    'STUDIO TERMINAL TIMING: For authorized compiler commands, use timeout_ms=120000 normally; '
    'for a cold cache or larger SDK compilation, allow up to timeout_ms=600000 within the tool limit. '
    'timeout_ms is the total process lifetime budget and terminates the process when reached. '
    'Use yield_time_ms=1000 for an early output return; it does not shorten the process lifetime. '
    'Do not use a one-second process timeout just to receive output quickly. Continue with the returned '
    'process handle via studio_write_stdin until its actual exit status is returned, rather than starting '
    'another compiler. Prefer the separately permitted studio_build_project for normal project builds; '
    'it waits internally for its original job. A longer budget is not a success guarantee or an instruction to wait unnecessarily.'
)


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
    from environment_note_tools import instructions as environment_instructions
    text += environment_instructions(config)
    from input_instructions import compose as input_instructions
    text += input_instructions(config)
    from goal_recovery import instructions as recovery_instructions
    text += recovery_instructions(config)
    from image_inputs import instructions as image_instructions
    text += image_instructions(config)
    from document_inputs import instructions as document_instructions
    text += document_instructions(config)
    from attachment_files import instructions as attachment_instructions
    text += attachment_instructions(config)
    from image_instructions import compose as image_generation_instructions
    text += image_generation_instructions(config)
    # Saved custom prompts remain original. Bound workers apply current timing
    # guidance without changing their frozen source text/revision/hash.
    if config.get('permissions', {}).get('studio.exec_command') and TERMINAL_TIMING not in text:
        text += '\n\n' + TERMINAL_TIMING
    from roadmap_instructions import compose as roadmap_instructions
    text += roadmap_instructions(config)
    from development_instructions import compose as development_instructions
    text += development_instructions(config)
    from remote_instructions import compose as remote_instructions
    text += remote_instructions(config)
    if 'skillAccess' not in config: return text
    from skill_application import catalog_text
    return text + catalog_text(config['skillAccess'])
