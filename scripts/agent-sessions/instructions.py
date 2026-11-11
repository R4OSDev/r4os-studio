"""Compose frozen global and project sources without native file discovery."""
import hashlib
import re
from pathlib import Path
from store import ProjectFault
from system_prompt import validate_text
from project_agents import NAME, validate

SDK_PROFILE_GUIDE = (Path(__file__).resolve().parents[2] / 'shared/project-sdk-profiles.txt').read_text().strip()

TERMINAL_TIMING = (
    'STUDIO TERMINAL TIMING: Use studio_build_project for normal project builds when permitted. '
    'timeout_ms sets the host process lifetime. In direct Studio runs the configured tool deadline also applies. '
    'Use tty or an explicit yield_time_ms to request a resumable process handle. '
    'Use studio_control_process on the returned handle to interact or read the exit status.'
)
TERMINAL_EXECUTION = (
    'STUDIO TERMINAL EXECUTION: For a finite noninteractive command, omit tty and yield_time_ms. '
    'Studio shows output while it runs and returns the final exit status. Use tty for an interactive '
    'terminal or set yield_time_ms when a resumable process handle is needed.'
)
TOOL_EXECUTION = (
    '\n\n*** STUDIO TOOL EXECUTION ***\n'
    'Studio runs tool calls in request order and returns every result together for the next step. '
    'Wait for that step when an argument depends on a result. A deadline failure can include partial output '
    'or a job ID. Read the original receipt before acting on possible partial effects.'
)


SECTION_HEADING = re.compile(
    r'^(?P<title>(?:CURRENT )?STUDIO [A-Z][A-Z0-9 /_-]*(?: v[0-9]+)?(?: \([^\n)]*\))?'
    r'|CURRENT CLEANUP CAPABILITY|ACCEPTED HUMAN PLAY OBJECTIVE \(JSON\)'
    r'|SENT ATTACHMENT MANIFEST \(task data, in Send order\))(?::[ \t]*|[ \t]*$)'
)


def format_sections(text):
    """Format generated Studio sections only; leave fenced examples intact."""
    result = []
    fence = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        marker = re.match(r'^\s*(`{3,}|~{3,})', body)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not body[marker.end():].strip():
                fence = None
            result.append(line)
            continue
        if marker:
            fence = marker[1]
            result.append(line)
            continue
        heading = SECTION_HEADING.match(body)
        if heading:
            remainder = body[heading.end():]
            result.append('*** ' + heading['title'].rstrip() + ' ***'
                          + ('\n' + remainder if remainder else '') + ending)
        else:
            result.append(line)
    return ''.join(result)


def base(config):
    if config.get('owner', {}).get('type') == 'skill':
        source = config.get('skillManagerPrompt', {})
        text = validate_text(source.get('text'))
        if hashlib.sha256(text.encode()).hexdigest() != source.get('sha256'):
            raise ProjectFault('The saved Skill Manager prompt checksum changed.', 409)
        return '*** STUDIO SKILL MANAGER INSTRUCTIONS ***\n' + text
    global_text = validate_text(config['systemPrompt']['text'])
    project = config.get('projectInstructions')
    if 'projectInstructions' not in config:
        # Already admitted legacy runs keep their original instruction source.
        return '*** GLOBAL R4OS STUDIO INSTRUCTIONS ***\n' + global_text
    if not isinstance(project, dict) or set(project) != {'path', 'text', 'sha256'} or project['path'] != NAME:
        raise ProjectFault('The saved project instructions snapshot is invalid.', 409)
    text = validate(project['text'])
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != project['sha256']:
        raise ProjectFault('The saved project instructions checksum changed.', 409)
    return ('*** GLOBAL R4OS STUDIO INSTRUCTIONS ***\n' + global_text +
            '\n\n*** PROJECT INSTRUCTIONS FROM Workspace/Agents.md ***\n' + text)


def compose(config, project=None):
    # Frozen instruction sources are opaque sections. Only generated additions
    # may be formatted; preserve source whitespace and internal headings verbatim.
    source = base(config)
    text = ''
    from goal_keepalive import instructions as keepalive_instructions
    text += keepalive_instructions(config)
    from active_tools import instructions as current_tool_instructions
    text += current_tool_instructions(config)
    if config['engine'].get('kind') == 'studio':
        text += ('\n\nSTUDIO FILE EDITS: Use JSON null as expectedSha256 for a new file. '
                 'For a replacement, read the exact SHA-256 first.')
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
    if (config.get('permissions', {}).get('studio.exec_command')
            and 'STUDIO TERMINAL TIMING' not in source and 'STUDIO TERMINAL TIMING' not in text):
        names=config.get('toolCatalog',{}).get('tools',[])
        terminal=TERMINAL_TIMING
        if 'studio_write_stdin' in names and 'studio_control_process' not in names:
            terminal=terminal.replace('studio_control_process','studio_write_stdin')
        elif 'studio_control_process' not in names:
            terminal=terminal.rsplit(' Use studio_control_process',1)[0]
        text += '\n\n' + terminal
    batch_results = config.get('toolDeadlines', {}).get('version') == 1
    if (not batch_results and config.get('terminalCompletion') == 1
            and config.get('permissions', {}).get('studio.exec_command')
            and config.get('apiProvider', {}).get('protocol') in ('responses', 'chat-completions')):
        text += '\n\n' + TERMINAL_EXECUTION
    from roadmap_instructions import compose as roadmap_instructions
    text += roadmap_instructions(config)
    from development_instructions import compose as development_instructions
    text += development_instructions(config)
    if (config.get('owner', {}).get('type') == 'project'
            and any(config.get('permissions', {}).get('studio.' + name) for name in ('read_file', 'search', 'exec_command', 'build_project'))
            and SDK_PROFILE_GUIDE not in source and SDK_PROFILE_GUIDE not in text):
        text += '\n\n' + SDK_PROFILE_GUIDE
    from remote_instructions import compose as remote_instructions
    text += remote_instructions(config)
    from shortcut_instructions import compose as shortcut_instructions
    text = shortcut_instructions(config, text, source)
    if 'skillAccess' in config:
        from skill_application import catalog_text
        text += catalog_text(config['skillAccess'], config.get('workspaceContext'),config)
    result_actions=config.get('toolCatalog',{}).get('actions',{}).get('studio_read_result',())
    if 'context' in result_actions:
        text += ('\n\nSTUDIO ORIGINAL RESULTS: Follow saved result references with studio_read_result. '
                 'Use context for JSON pages, image for a saved image and index for checkpoint references.')
    from workspace_instructions import compose as workspace_guidance
    generated = format_sections(text + runtime_guidance(config, project) + workspace_guidance(config))
    return source + generated + (TOOL_EXECUTION if batch_results else '')


def runtime_guidance(config, project=None):
    rights = config.get('permissions', {})
    text = ''
    if config.get('webSearchEnabled') is True:
        text += ('\n\nSTUDIO WEB SEARCH: Use the declared web tool for external sources when needed. '
                 'Cite the sources used and keep private data out of queries.')
    if config.get('owner', {}).get('type') != 'project':
        return text
    if project is not None and any(rights.get('studio.' + name) for name in ('build_project', 'deploy_project', 'run_project', 'exec_command')):
        from environment_instructions import compose as environment
        text += environment(project, config)
    if rights.get('studio.capture_vm'):
        text += ('\n\nSTUDIO IMAGES: Use the returned presentation.markdown to show a requested screenshot. '
                 'Base visual claims on the received image or the attributed Vision analysis. Pass analysisQuestion '
                 'for an available Vision fallback when the main model needs it.')
        if (config.get('vmObservation') or {}).get('available') is True:
            text += (' Use scope="vm" for an explicit VM diagnostic on the assigned running VM. '
                     'Use an owned app frame to verify app behavior.')
    if any(rights.get('studio.' + name) for name in ('send_vm_input', 'control_app_window')):
        text += ('\n\nSTUDIO GUI: Use a fresh focused frame of the owned app for input. Capture a current frame '
                 'after a view change. Check the original receipt and observe the app after an action.')
    from profile import UPDATE_TOOLS
    if any(rights.get('studio.' + name) for name in UPDATE_TOOLS):
        text += ('\n\nSTUDIO UPDATES: Use the R4OS Update Packages skill when available. Review the original package, '
                 'transfer, native check and installation receipts. Obtain user authorization for the specific reboot or rollback.')
    return text
