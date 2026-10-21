"""Stable Studio dynamic tool declarations; authorization is checked for every call."""
from profile import TOOLS


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


STR = {'type': 'string'}
PATH = {'type': 'string', 'maxLength': 1024, 'description': 'Relative path within the chosen root; use . for its directory.'}
ROOT = {'type': 'string', 'enum': ['workspace', 'sdk', 'contract', 'zig', 'rust'], 'description': 'workspace is writable; pinned component roots are read-only.'}
DEFS = {
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
 'search': ('Search filenames or literal text within the selected root. Results are bounded; no shell expansion.',
   obj({'path': PATH, 'root': ROOT, 'query': {'type': 'string', 'maxLength': 200}, 'filenames': {'type': 'boolean'}}, ['query'])),
 'write_file': ('Create or replace a UTF-8 project file through Studio. Supply expectedSha256 for an existing file, or null for a new file. Writes are allowed only in workspace.',
   obj({'path': PATH, 'content': {'type': 'string', 'maxLength': 65536}, 'expectedSha256': {'type': ['string', 'null']}}, ['path', 'content', 'expectedSha256'])),
 'apply_patch': ('Apply a Codex-format patch in workspace using the official parser. Supply expectedHashes for each existing source file changed/deleted/moved. Partial changes are reported if a later patch entry fails.',
   obj({'patch': {'type': 'string', 'maxLength': 65536}, 'expectedHashes': {'type': 'object', 'additionalProperties': {'type': 'string'}}}, ['patch', 'expectedHashes'])),
 'create_directory': ('Create a directory inside workspace.', obj({'path': PATH}, ['path'])),
}


def specifications():
    # The protocol persists dynamic declarations on first thread creation. Keep
    # the known set stable on resume; disabled/unavailable calls fail in the host
    # dispatcher BEFORE execution, even if the model retains their declarations.
    return [{'name': 'studio_' + name, 'description': DEFS[name][0], 'inputSchema': DEFS[name][1]} for name in TOOLS]


def validate_arguments(name, value):
    def validate(rule, v):
        types = rule['type'] if isinstance(rule['type'], list) else [rule['type']]
        actual = 'null' if v is None else ('boolean' if type(v) is bool else ('integer' if type(v) is int else ('string' if isinstance(v, str) else ('object' if isinstance(v, dict) else 'invalid'))))
        if actual not in types: raise ValueError('Invalid tool argument type.')
        if actual == 'string':
            if '\x00' in v or len(v.encode()) > rule.get('maxLength', 8192): raise ValueError('Tool argument exceeds its limit.')
            if 'enum' in rule and v not in rule['enum']: raise ValueError('Unknown tool argument.')
        if actual == 'integer' and not rule.get('minimum', 0) <= v <= rule.get('maximum', 1000000): raise ValueError('Tool argument exceeds its range.')
        if actual == 'object':
            if len(v) > 64 or not set(rule.get('required', [])).issubset(v): raise ValueError('Missing tool arguments.')
            for key, entry in v.items():
                spec = rule.get('properties', {}).get(key, rule.get('additionalProperties', False))
                if not isinstance(spec, dict): raise ValueError('Unknown tool argument.')
                validate(spec, entry)
    validate(DEFS[name][1], value)
