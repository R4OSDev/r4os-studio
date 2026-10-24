"""Version-bound file operations with private staging and durable request receipts."""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from editor_files import MAX_TEXT, node, parent, parts, revision, root_path
from layout import folder, save, sync
from project_use import acquire, project_id
from project_maintenance import require_idle
from store import ProjectFault


def storage(projects, identity):
    base = Path(projects) / identity
    for name in ('.studio', '.studio/editor', '.studio/editor/Requests', '.studio/editor/Stage'):
        path = base / name
        path.mkdir(mode=0o700, exist_ok=True); folder(path)
        sync(path.parent)
    return base / '.studio/editor'


def document(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 32768:
            raise ProjectFault('Invalid editor operation receipt.', 503)
        return json.loads(stream.read(32769))


def receipt(projects, identity, request_id):
    project_id(request_id)
    base = Path(projects) / identity / '.studio/editor'
    for path in (base.parent, base, base / 'Requests'):
        if path.exists() or path.is_symlink(): folder(path)
    path = base / 'Requests' / (request_id + '.json')
    if not path.exists() and not path.is_symlink(): return {'requestId': request_id, 'state': 'missing'}
    value = document(path)
    if value.get('schema') != 1 or value.get('projectId') != identity or value.get('requestId') != request_id:
        raise ProjectFault('Invalid editor operation identity.', 503)
    return value.get('result') or {'requestId': request_id, 'state': 'unknown', 'kind': value['kind'],
                                  'path': value['path'], 'message': 'The operation needs an explicit retry to reconcile its result.'}


def no_replace(source_fd, source, target_fd, target):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1):
        code = ctypes.get_errno()
        if code == errno.EEXIST: raise ProjectFault('The destination already exists. Choose another path.', 409)
        raise OSError(code, os.strerror(code))


def file_identity(info): return [info.st_dev, info.st_ino]


def same_entry(descriptor, name, expected):
    try: return file_identity(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) == expected
    except FileNotFoundError: return False


def validate(data):
    if not isinstance(data, dict): raise ProjectFault('Invalid editor mutation.', 400)
    kind = data.get('kind')
    required = {'requestId', 'kind', 'path'}
    if kind == 'save': required |= {'expected', 'text', 'format'}
    elif kind == 'create': required |= {'text'} | ({'format'} if 'format' in data else set())
    elif kind == 'mkdir': pass
    elif kind == 'rename': required |= {'expected', 'target'}
    elif kind == 'delete': required |= {'expected', 'confirm'}
    else: raise ProjectFault('Unsupported editor mutation.', 400)
    if set(data) != required: raise ProjectFault('Unexpected editor mutation fields.', 400)
    project_id(data['requestId']); parts(data['path'], new=kind in ('create', 'mkdir'))
    if kind == 'rename':
        parts(data['target'], new=True)
        if data['target'] == data['path'] or data['target'].startswith(data['path'] + '/'):
            raise ProjectFault('Choose a different destination outside the source directory.', 400)
    if kind == 'delete' and data['confirm'] is not True: raise ProjectFault('Confirm deletion of this entry.', 400)
    if kind == 'mkdir' and data['path'].casefold() == 'agents.md':
        raise ProjectFault('Agents.md must be a regular instruction file.', 400)
    if 'expected' in data:
        expected = data['expected']
        if (not isinstance(expected, dict) or set(expected) - {'revision', 'sha256'} or
                not isinstance(expected.get('revision'), str) or not re.fullmatch('[a-f0-9]{64}', expected['revision']) or
                ('sha256' in expected and (not isinstance(expected['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', expected['sha256'])))):
            raise ProjectFault('A current file identity is required.', 400)
    raw = None
    if kind in ('save', 'create'):
        text = data['text']
        if not isinstance(text, str) or any(ord(c) < 32 and c not in '\t\n' or ord(c) == 127 for c in text):
            raise ProjectFault('Use UTF-8 editor text with LF document separators.', 400)
        fmt = data.get('format', {'bom': False, 'eol': 'lf'})
        if (not isinstance(fmt, dict) or set(fmt) != {'bom', 'eol'} or type(fmt['bom']) is not bool or fmt['eol'] not in ('lf', 'crlf')):
            raise ProjectFault('Invalid document format.', 400)
        raw = (('\ufeff' if fmt['bom'] else '') + (text.replace('\n', '\r\n') if fmt['eol'] == 'crlf' else text)).encode('utf-8')
        if len(raw) > MAX_TEXT: raise ProjectFault('The document exceeds 512 KiB.', 413)
        if data['path'].casefold() == 'agents.md':
            from project_agents import validate as validate_agents
            validate_agents(raw.decode('utf-8'))
    return kind, raw


def checked_node(root, data):
    value = node(root, data['path'], content=data['kind'] == 'save')
    if data['kind'] in ('create', 'mkdir'):
        if value['kind'] != 'missing': raise ProjectFault('The destination already exists.', 409)
    else:
        if value.get('revision') != data['expected']['revision']:
            raise ProjectFault('The entry changed. Reload or compare the current version.', 409)
        if value['kind'] not in ('file', 'directory') or value.get('reason'):
            raise ProjectFault(value.get('reason', 'This entry cannot be changed.'), 409)
        if data['kind'] == 'save':
            if not value.get('editable') or value.get('sha256') != data['expected'].get('sha256'):
                raise ProjectFault('The file changed or cannot be edited. Reload or compare it.', 409)
            if value['format'] != data['format']:
                raise ProjectFault('Preserve the original file format.', 409)
    if data['path'].casefold() == 'agents.md' or data.get('target', '').casefold() == 'agents.md':
        if any(name.casefold() == 'agents.md' and name != 'Agents.md' for name in os.listdir(root)):
            raise ProjectFault('Resolve the conflicting Agents.md filename first.', 409)
        if data['path'].casefold() == 'agents.md' and data['path'] != 'Agents.md' or data.get('target', '').casefold() == 'agents.md' and data.get('target') != 'Agents.md':
            raise ProjectFault('Use the filename Agents.md.', 400)
        if data['kind'] == 'rename' and data.get('target') == 'Agents.md':
            content = node(root, data['path'], content=True)
            if not content.get('editable'): raise ProjectFault('Only valid project instruction text can become Agents.md.', 409)
            from project_agents import validate as validate_agents
            fmt = content['format']
            validate_agents(('\ufeff' if fmt['bom'] else '') + (content['text'].replace('\n', '\r\n') if fmt['eol'] == 'crlf' else content['text']))
    return value


def mutate(projects, identity, data, hosts):
    kind, raw = validate(data)
    request_id = data['requestId']
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with acquire(projects, identity, exclusive=True):
        workspace = root_path(projects, identity)
        base = storage(projects, identity); journal = base / 'Requests' / (request_id + '.json')
        record = document(journal) if journal.exists() or journal.is_symlink() else None
        recovering = record is not None
        if record and (record.get('schema') != 1 or record.get('projectId') != identity or record.get('requestId') != request_id or record.get('requestHash') != fingerprint):
            raise ProjectFault('This editor request ID belongs to a different operation.', 409)
        if record and record.get('phase') not in ('prepared', 'staged', 'committing', 'published'):
            raise ProjectFault('Invalid editor operation phase. Host maintenance is required.', 503)
        if record and record.get('result'): return record['result']
        require_idle(projects, identity)
        from clear_cache import worker_admission
        worker_admission(projects, identity, hosts, 'editing Workspace files')
        root = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stage = os.open(base / 'Stage', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        par = dest = None
        try:
            par, name = parent(root, data['path'])
            if os.fstat(par).st_dev != os.fstat(stage).st_dev:
                raise ProjectFault('Editor staging and Workspace must use the same filesystem.', 409)
            dest, target = parent(root, data['target']) if kind == 'rename' else (os.dup(par), name)
            if os.fstat(dest).st_dev != os.fstat(stage).st_dev: raise ProjectFault('The destination is on another filesystem.', 409)
            slot = request_id
            if record is None:
                current = checked_node(root, data)
                if kind == 'rename' and node(root, data['target'])['kind'] != 'missing': raise ProjectFault('The destination already exists.', 409)
                if kind == 'delete' and current['kind'] == 'directory':
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=par)
                    try:
                        if os.listdir(child): raise ProjectFault('Only empty folders can be deleted.', 409)
                    finally: os.close(child)
                if os.path.lexists(base / 'Stage' / slot): raise ProjectFault('Unattributed editor staging was preserved.', 409)
                record = {'schema': 1, 'projectId': identity, 'requestId': request_id, 'requestHash': fingerprint,
                          'kind': kind, 'path': data['path'], 'target': data.get('target'), 'phase': 'prepared',
                          'workspaceIdentity': file_identity(os.fstat(root)),
                          'original': file_identity(os.stat(name, dir_fd=par, follow_symlinks=False)) if current['kind'] != 'missing' else None}
                save(journal, record)
            if record['workspaceIdentity'] != file_identity(os.fstat(root)):
                raise ProjectFault('The Workspace identity changed. The old operation was preserved.', 409)

            def finish(state, message=None):
                value = {'requestId': request_id, 'kind': kind, 'path': data['path'], 'target': data.get('target'), 'state': state}
                if message: value['message'] = message
                if state == 'complete':
                    result_node = node(root, data.get('target', data['path']), content=recovering and kind in ('save', 'create'))
                    result_node.pop('text', None)
                    if raw is not None and not recovering: result_node['sha256'] = hashlib.sha256(raw).hexdigest()
                    value['node'] = result_node
                if state == 'rejected' and kind in ('save', 'create', 'mkdir') and record.get('staged') and same_entry(stage, slot, record['staged']):
                    if kind == 'mkdir': os.rmdir(slot, dir_fd=stage)
                    else: os.unlink(slot, dir_fd=stage)
                    os.fsync(stage)
                if state != 'unknown': record['result'] = value
                save(journal, record)
                return value

            if record['phase'] in ('prepared', 'staged'):
                try: checked_node(root, data)
                except ProjectFault as error:
                    return finish('rejected', str(error))
                if kind in ('save', 'create', 'mkdir'):
                    if record['phase'] == 'prepared':
                        # This private reserved slot is invisible to agent tools.
                        if os.path.lexists(base / 'Stage' / slot):
                            info = os.stat(slot, dir_fd=stage, follow_symlinks=False)
                            if stat.S_ISDIR(info.st_mode): os.rmdir(slot, dir_fd=stage)
                            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1: os.unlink(slot, dir_fd=stage)
                            else: return finish('unknown', 'Private staging changed. Host maintenance is required.')
                        if kind == 'mkdir': os.mkdir(slot, 0o755, dir_fd=stage)
                        else:
                            old_mode = stat.S_IMODE(os.stat(name, dir_fd=par, follow_symlinks=False).st_mode) if kind == 'save' else 0o644
                            fd = os.open(slot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, old_mode, dir_fd=stage)
                            with os.fdopen(fd, 'wb') as stream:
                                stream.write(raw); stream.flush(); os.fchmod(stream.fileno(), old_mode); os.fsync(stream.fileno())
                        os.fsync(stage)
                        record.update(phase='staged', staged=file_identity(os.stat(slot, dir_fd=stage, follow_symlinks=False)))
                        save(journal, record)
                checked_node(root, data)
                record['phase'] = 'committing'; save(journal, record)

            if record['phase'] == 'committing':
                present = os.path.lexists(base / 'Stage' / slot)
                if kind in ('save', 'create', 'mkdir'):
                    if present:
                        if not same_entry(stage, slot, record['staged']): return finish('unknown', 'Private staging identity changed.')
                        try: checked_node(root, data)
                        except ProjectFault as error: return finish('rejected', str(error))
                        if kind == 'save': os.replace(slot, target, src_dir_fd=stage, dst_dir_fd=dest)
                        else: no_replace(stage, slot, dest, target)
                    # Consuming the reserved stage proves publication even if
                    # a later writer has since replaced the destination.
                elif kind == 'rename':
                    if same_entry(dest, target, record['original']) and not same_entry(par, name, record['original']): pass
                    else:
                        try: checked_node(root, data)
                        except ProjectFault as error: return finish('unknown', str(error))
                        no_replace(par, name, dest, target)
                else:
                    if present:
                        if not same_entry(stage, slot, record['original']): return finish('unknown', 'Detached entry identity changed.')
                    else:
                        try: checked_node(root, data)
                        except ProjectFault as error: return finish('unknown', str(error))
                        no_replace(par, name, stage, slot)
                os.fsync(par); os.fsync(dest); os.fsync(stage)
                record['phase'] = 'published'; save(journal, record)
            if record['phase'] == 'published' and kind == 'delete' and os.path.lexists(base / 'Stage' / slot):
                if not same_entry(stage, slot, record['original']): return finish('unknown', 'Detached entry identity changed.')
                info = os.stat(slot, dir_fd=stage, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    try: os.rmdir(slot, dir_fd=stage)
                    except OSError as error:
                        if error.errno != errno.ENOTEMPTY: raise
                        no_replace(stage, slot, par, name); os.fsync(par); os.fsync(stage)
                        return finish('rejected', 'The folder is not empty. Its contents were preserved.')
                else: os.unlink(slot, dir_fd=stage)
                os.fsync(stage)
            return finish('complete')
        except (OSError, ProjectFault) as error:
            if record:
                return {'requestId': request_id, 'kind': kind, 'path': data['path'], 'state': 'unknown',
                        'message': 'The editor operation needs retry: ' + str(error)[:500]}
            raise
        finally:
            if dest is not None: os.close(dest)
            if par is not None: os.close(par)
            os.close(stage); os.close(root)
