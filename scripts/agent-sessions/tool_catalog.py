"""Stable Studio dynamic tool declarations; authorization is checked for every call."""
from profile import TOOLS, PROFILE, SKILL_PROFILES, tools_for
from copy import deepcopy


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


STR = {'type': 'string'}
PATH = {'type': 'string', 'maxLength': 1024, 'description': 'Relative path within the chosen root; use . for its directory.'}
ROOT = {'type': 'string', 'enum': ['workspace', 'sdk', 'contract', 'zig', 'rust'], 'description': 'workspace is writable; pinned component roots are read-only.'}
DEFS = {
 'push_project': ('Commit saved changes in this project and push its bound GitHub branch without force. A nonempty commitMessage is required. Optional files selects relative saved source paths; omitted means all saved changes. Finish live terminal/development work first. This call waits in the harness for the original Git job and verified remote receipt. Tokens and general Git/network access are never exposed. Do not repeat an unconfirmed effect.', obj({'commitMessage': {'type': 'string', 'minLength': 1, 'maxLength': 4000}, 'files': {'type': 'array', 'maxItems': 128, 'items': PATH}}, ['commitMessage'])),
 'exec_command': ('Run a command in the separate Studio project sandbox. cwd defaults to /workspace. Network is unavailable. Native Codex shell tools are unavailable. Return output and a process handle if still running.',
   obj({'cmd': {'type': 'string', 'maxLength': 16384}, 'workdir': PATH, 'tty': {'type': 'boolean'},
        'yield_time_ms': {'type': 'integer', 'minimum': 100, 'maximum': 10000}, 'timeout_ms': {'type': 'integer', 'minimum': 100, 'maximum': 600000}}, ['cmd'])),
 'write_stdin': ('Read more output or send input/EOF to this run\'s process. Poll a running process until its actual exit status is returned.',
   obj({'processId': STR, 'chars': {'type': 'string', 'maxLength': 8192}, 'closeStdin': {'type': 'boolean'},
        'yield_time_ms': {'type': 'integer', 'minimum': 100, 'maximum': 10000}}, ['processId'])),
 'terminate_process': ('Terminate this run\'s process and its descendants.', obj({'processId': STR}, ['processId'])),
 'list_directory': ('List a project directory or pinned read-only component directory. Results are bounded and paginated.',
   obj({'path': PATH, 'root': ROOT, 'offset': {'type': 'integer', 'minimum': 0}}, ['path'])),
 'read_file': ('Read UTF-8 source text with line numbers and its SHA-256 for conflict-protected writes. This is Studio broker access, independent of Codex native filesystem tools.',
   obj({'path': PATH, 'root': ROOT, 'startLine': {'type': 'integer', 'minimum': 1}, 'maxLines': {'type': 'integer', 'minimum': 1, 'maximum': 500}}, ['path'])),
 'search': ('Search filenames or literal UTF-8 text in a regular file or directory within the selected root. Directories are traversed within fixed file/byte/result/time limits; no links or special files. Skipped files and incomplete results are reported. No shell expansion.',
   obj({'path': PATH, 'root': ROOT, 'query': {'type': 'string', 'maxLength': 200}, 'filenames': {'type': 'boolean'}}, ['query'])),
 'write_file': ('Create or replace a UTF-8 project file through Studio. Supply expectedSha256 for an existing file, or null for a new file. Writes are allowed only in workspace.',
   obj({'path': PATH, 'content': {'type': 'string', 'maxLength': 65536}, 'expectedSha256': {'type': ['string', 'null']}}, ['path', 'content', 'expectedSha256'])),
 'apply_patch': ('Apply a Codex-format patch in workspace using the official parser. Supply expectedHashes for each existing source file changed/deleted/moved. Partial changes are reported if a later patch entry fails.',
   obj({'patch': {'type': 'string', 'maxLength': 65536}, 'expectedHashes': {'type': 'object', 'additionalProperties': {'type': 'string'}}}, ['patch', 'expectedHashes'])),
 'create_directory': ('Create a directory inside workspace.', obj({'path': PATH}, ['path'])),
}

ID = {'type': 'string', 'maxLength': 36, 'description': 'Opaque Studio UUID from a confirmed tool result.'}
FILE_CRITERION = obj({'name': {'type': 'string', 'maxLength': 12}, 'contains': {'type': ['string', 'null'], 'maxLength': 1024},
    'sha256': {'type': ['string', 'null'], 'maxLength': 64}}, ['name', 'contains', 'sha256'])
CRITERIA = obj({'expectedExitCode': {'type': ['integer', 'null'], 'minimum': -2147483648, 'maximum': 2147483647},
    'outputContains': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string', 'maxLength': 256}},
    'outputFiles': {'type': 'array', 'maxItems': 8, 'items': FILE_CRITERION},
    'serviceResponseContains': {'type': ['string', 'null'], 'maxLength': 256},
    'visualCriteria': {'type': 'string', 'maxLength': 1024}})
DEFS.update({
 'validate_skill': ('Validate the complete current selected skill draft without running scripts. Returns concrete catalog revision, draftHash, relative files and diagnostics. An optional expectedDraftHash detects a changed draft. Wait for all run terminals to finish before validation.', obj({'expectedDraftHash': {'type': 'string', 'maxLength': 64}})),
 'save_skill': ('Publish the same validated complete selected skill draft as a global immutable revision. Use revision and draftHash from validate_skill, preserve drafts if invalid, and report only the confirmed returned activeRevision/activeHash. No scripts run. Only publish when requested; draft-only requests stay drafts. Never repeat an unknown save.', obj({'revision': {'type': 'integer', 'minimum': 1, 'maximum': 9007199254740991}, 'draftHash': {'type': 'string', 'maxLength': 64}}, ['revision', 'draftHash'])),
 'start_project_vm': ('Start only this project\'s assigned VM if stopped, or use its current boot if already running. This single tool call waits in the Studio harness until the fixed R4OS default account authenticates over SSH and R4OS answers VER, then resumes this agent turn with a durable readiness receipt. Studio supplies the login automatically; never ask the user to enter credentials. Do not poll, sleep, or repeatedly call start while it waits. SSH readiness does not prove GUI or app readiness. Requires Network and enabled development access; never changes VM settings or deploys files.', obj({})),
 'build_project': ('Build an immutable snapshot of this project with its pinned offline SDK/compiler. Finish all live terminal commands first. This call waits in the harness until the original build completes and returns its artifactId or terminal error. The durable job link and progress appear immediately. Do not poll, sleep or resubmit while it waits. No VM action.', obj({})),
 'deploy_project': ('Transfer this session\'s verified artifact to its already running, SSH-ready assigned VM and verify every byte. First use the separately permitted start_project_vm tool when available and wait for its readiness receipt. Never starts the VM or app and never changes Network/image/settings. This call waits in the harness for the original verified deployment or terminal error; use its deploymentId without polling or resubmitting.', obj({'artifactId': ID}, ['artifactId'])),
 'run_project': ('Start this session\'s verified deployment once with its qualified role. Optional arguments/time/criteria override only this job, not saved project settings. Background execution remains bounded after this agent turn. Poll actual output/status/check; an accepted start/window alone is not a test pass.', obj({'deploymentId': ID,
    'arguments': {'type': 'string', 'maxLength': 1024}, 'timeoutSeconds': {'type': 'integer', 'minimum': 1, 'maximum': 300},
    'criteria': CRITERIA}, ['deploymentId'])),
 'read_development_job': ('Read this session\'s durable build/deploy/execution status, bounded output page, artifact/deployment IDs, criteria and evidence. offset is a byte cursor; continue from nextOffset. No command is started or repeated. Use waitMilliseconds to pause between polls.', obj({'jobId': ID, 'offset': {'type': 'integer', 'minimum': 0, 'maximum': 2097152}, 'waitMilliseconds': {'type': 'integer', 'minimum': 0, 'maximum': 10000}}, ['jobId'])),
 'complete_development_job': ('Explicitly complete this session\'s live test only after every configured criterion is confirmed. Closes only its owned process generation and waits for confirmed cleanup; use this after image assessment before reporting the test complete. Requires completion, run and stop permissions. Does not change the real exit code or turn timeouts into success. Do not repeat an unconfirmed completion; inspect the original job.', obj({'jobId': ID}, ['jobId'])),
 'stop_development_job': ('Stop this session\'s development job and only its owned process generation. Does not stop/reset/delete the VM or affect another session. User Stop is independent of this permission.', obj({'jobId': ID}, ['jobId'])),
 'capture_vm': ('Capture the assigned VM as an actual native image for this session\'s job. Image-capable models only. Includes time, boot/process, image ID, dimensions and GUI revision. When asked for a screenshot, embed the returned presentation.markdown in your reply to show the stored image outside tool calls. Reuse confirmed references without another capture. Inspect the image before GUI input. action=assess records an attributed visual judgment against explicit criteria using an image captured in this agent run; requires evidenceId/state/notes.', obj({'jobId': ID,
    'action': {'type': 'string', 'enum': ['capture', 'assess']}, 'evidenceId': ID,
    'state': {'type': 'string', 'enum': ['passed', 'failed', 'inconclusive']}, 'notes': {'type': 'string', 'maxLength': 1024}}, ['jobId'])),
 'send_vm_input': ('Queue bounded input for this session\'s live owned process. Console text requires the app\'s R4DESK console-event reader. GUI key/click requires a focused window and its image frameId from the last 30 seconds. Coordinates are client-relative. Accepted events do not prove application consumption; verify output/files/new image. No shell, QMP, paste or global input.', obj({'jobId': ID,
    'kind': {'type': 'string', 'enum': ['text', 'key', 'click']}, 'text': {'type': 'string', 'maxLength': 256},
    'key': {'type': 'string', 'enum': ['Enter', 'Tab', 'Escape', 'Space']}, 'frameId': ID,
    'x': {'type': 'integer', 'minimum': 0, 'maximum': 1279}, 'y': {'type': 'integer', 'minimum': 0, 'maximum': 1023}}, ['jobId', 'kind'])),
})


from update_catalog import DEFS as UPDATE_DEFS
DEFS.update(UPDATE_DEFS)

def specifications(profile=PROFILE):
    # The protocol persists dynamic declarations on first thread creation. Keep
    # the known set stable on resume; disabled/unavailable calls fail in the host
    # dispatcher BEFORE execution, even if the model retains their declarations.
    result = []
    for name in tools_for(profile):
        description, schema = DEFS[name][0], deepcopy(DEFS[name][1])
        if profile == PROFILE and name == 'send_vm_input':
            description = ('Queue bounded events only for this session\'s owned process. kind=text is console input; '
                'kind=guiText sends up to 64 Unicode characters/256 UTF-8 bytes to the focused GUI window. '
                'GUI text, key and click require its image frameId from the last 30 seconds. '
                'key accepts a printable ASCII character or Enter, Tab, Shift+Tab, Escape, Space, Backspace, Delete, '
                'ArrowUp/Down/Left/Right, Home, End, PageUp/Down. Optional repeat=1..16 is key-only, not a held key. '
                'Extended input requires a newly deployed GUI-input-v2 helper. Coordinates are client-relative. '
                'Inspect accepted/expected/complete; partial acceptance must not be blindly repeated. '
                'Acceptance does not prove application consumption; verify a new image/output. No global input or clipboard paste.')
            schema['properties']['kind']['enum'] = ['text', 'guiText', 'key', 'click']
            schema['properties']['key'] = {'type': 'string', 'minLength': 1, 'maxLength': 32}
            schema['properties']['repeat'] = {'type': 'integer', 'minimum': 1, 'maximum': 16}
        if profile in SKILL_PROFILES:
            description = description.replace('project', 'selected skill')
            if 'root' in schema['properties']:
                schema['properties']['root'] = {'type': 'string', 'enum': ['workspace'], 'description': 'Only the selected skill draft is available.'}
        result.append({'name': 'studio_' + name, 'description': description, 'inputSchema': schema})
    return result


def validate_arguments(name, value, profile=PROFILE):
    def validate(rule, v):
        types = rule['type'] if isinstance(rule['type'], list) else [rule['type']]
        actual = 'null' if v is None else ('boolean' if type(v) is bool else ('integer' if type(v) is int else ('string' if isinstance(v, str) else ('object' if isinstance(v, dict) else ('array' if isinstance(v, list) else 'invalid')))))
        if actual not in types: raise ValueError('Invalid tool argument type.')
        if actual == 'string':
            if '\x00' in v or not rule.get('minLength', 0) <= len(v.encode()) <= rule.get('maxLength', 8192): raise ValueError('Tool argument exceeds its limit.')
            if 'enum' in rule and v not in rule['enum']: raise ValueError('Unknown tool argument.')
        if actual == 'integer' and not rule.get('minimum', 0) <= v <= rule.get('maximum', 1000000): raise ValueError('Tool argument exceeds its range.')
        if actual == 'array':
            if len(v) > rule.get('maxItems', 8): raise ValueError('Too many tool arguments.')
            for entry in v: validate(rule['items'], entry)
        if actual == 'object':
            if len(v) > 64 or not set(rule.get('required', [])).issubset(v): raise ValueError('Missing tool arguments.')
            for key, entry in v.items():
                spec = rule.get('properties', {}).get(key, rule.get('additionalProperties', False))
                if not isinstance(spec, dict): raise ValueError('Unknown tool argument.')
                validate(spec, entry)
    definition = next((v for v in specifications(profile) if v['name'] == 'studio_' + name), None)
    if definition is None: raise ValueError('Unknown tool for this session profile.')
    validate(definition['inputSchema'], value)
