"""Bounded literal Workspace search, without shells, links or background indexing."""
import os
import stat
import time
from editor_files import MAX_TEXT, directory, node, parts, revision, signature
from store import ProjectFault

EXCLUDED = {'.git', '.zig-cache', 'zig-out', 'zig-pkg', 'target', 'build', '.R4OSRust', 'node_modules'}
LIMITS = {'files': 2000, 'directories': 2000, 'entries': 10000, 'bytes': 16 * 1024 * 1024, 'matches': 200, 'seconds': 3}


def search(root, data):
    if (set(data) - {'query', 'mode', 'caseSensitive'} or not {'query', 'mode'} <= set(data) or
            data['mode'] not in ('name', 'content') or not isinstance(data['query'], str) or
            len(data['query']) > 200 or len(data['query'].encode('utf-8')) > 800 or
            any(ord(c) < 32 or ord(c) == 127 for c in data['query']) or type(data.get('caseSensitive', False)) is not bool):
        raise ProjectFault('Use a single-line search of at most 200 characters.', 400)
    query, mode, sensitive = data['query'], data['mode'], data.get('caseSensitive', False)
    if mode == 'content' and not query.strip(): raise ProjectFault('Enter text to search for.', 400)
    needle = query if sensitive else query.casefold()
    result = {'entries': [], 'incomplete': False, 'scannedFiles': 0, 'scannedBytes': 0,
              'scannedDirectories': 0, 'skipped': 0, 'excluded': 0, 'limits': LIMITS, 'excludedDirectories': sorted(EXCLUDED)}
    pending, entries_seen, deadline = [''], 0, time.monotonic() + LIMITS['seconds']

    def stop():
        return (entries_seen >= LIMITS['entries'] or result['scannedFiles'] >= LIMITS['files'] or
                len(result['entries']) >= LIMITS['matches'] or time.monotonic() >= deadline)

    while pending:
        if stop(): result['incomplete'] = True; break
        path = pending.pop()
        try: descriptor = directory(root, path)
        except OSError:
            result['skipped'] += 1; result['incomplete'] = True; continue
        try:
            result['scannedDirectories'] += 1
            before, names = os.fstat(descriptor), []
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    if entries_seen >= LIMITS['entries'] or time.monotonic() >= deadline:
                        result['incomplete'] = True; break
                    names.append(entry.name); entries_seen += 1
            names.sort(key=lambda value: (value.casefold(), value))
            for name in names:
                if (result['scannedFiles'] >= LIMITS['files'] or len(result['entries']) >= LIMITS['matches'] or time.monotonic() >= deadline):
                    result['incomplete'] = True; break
                relative = path + '/' + name if path else name
                try:
                    parts(relative)
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        if name in EXCLUDED: result['excluded'] += 1; continue
                        if result['scannedDirectories'] + len(pending) >= LIMITS['directories']:
                            result['incomplete'] = True; continue
                        pending.append(relative); continue
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        result['skipped'] += 1; continue
                    result['scannedFiles'] += 1
                    if mode == 'name':
                        if needle in (relative if sensitive else relative.casefold()):
                            result['entries'].append({'path': relative, 'revision': revision(info)})
                        continue
                    if info.st_size > MAX_TEXT: result['skipped'] += 1; continue
                    remaining = LIMITS['bytes'] - result['scannedBytes']
                    if info.st_size > remaining:
                        result['incomplete'] = True; pending.clear(); break
                    try: file = node(root, relative, content=True, byte_limit=remaining)
                    except (OSError, ProjectFault):
                        # A failed stable read may already have consumed its
                        # entire allowance. Charge it before continuing.
                        result['scannedBytes'] += min(MAX_TEXT, remaining)
                        raise
                    if file.get('sha256'): result['scannedBytes'] += file['bytes']
                    if 'text' not in file:
                        result['skipped'] += 1
                        if file.get('bytes', 0) > remaining: result['incomplete'] = True
                        continue
                    for line, text in enumerate(file['text'].replace('\r', '\n').split('\n'), 1):
                        if time.monotonic() >= deadline or len(result['entries']) >= LIMITS['matches']:
                            result['incomplete'] = True; break
                        index = (text if sensitive else text.casefold()).find(needle)
                        if index >= 0:
                            start = max(0, index - 80)
                            preview = ('…' if start else '') + text[start:start + 240]
                            result['entries'].append({'path': relative, 'revision': file['revision'], 'line': line, 'preview': preview})
                except (OSError, ProjectFault):
                    result['skipped'] += 1; result['incomplete'] = True
            if signature(os.fstat(descriptor)) != signature(before): result['incomplete'] = True
        finally: os.close(descriptor)
    return result
