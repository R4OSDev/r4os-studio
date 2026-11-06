"""Bounded seeks over original log bytes; derived previews consume no cursor."""
import hashlib
import json
import os
import re
import stat
from contracts import DevelopmentFault, LIMITS

MAX_TAIL = 8192
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
ERROR = re.compile(rb'(?mi)^[^\r\n]{0,160}?(?:error\[E[0-9]{4}\]|(?:fatal )?error:)')


def read(path, count):
    if type(count) is not int or not 1 <= count <= MAX_TAIL:
        raise DevelopmentFault('tailBytes must be an integer between 1 and 8192.', 400)
    if not path.exists() and not path.is_symlink():
        return b'', {'source': 'original-output-log', 'state': 'missing', 'startOffset': 0, 'totalBytes': 0, 'nextOffset': 0, 'pageBytes': 0}
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid development log path.', 503)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > LIMITS['outputBytes']:
            raise DevelopmentFault('Invalid development log or capture budget.', 503)
        requested = max(0, before.st_size - count); position = max(0, requested - 3)
        stream.seek(position); data = stream.read(before.st_size - position)
        after = os.fstat(stream.fileno())
    start = requested; index = requested - position
    # Skip only a confirmed split UTF-8 codepoint; arbitrary binary stays exact.
    for lead in range(max(0, index - 3), min(index, len(data))):
        first = data[lead]; width = 2 if 0xc2 <= first <= 0xdf else 3 if 0xe0 <= first <= 0xef else 4 if 0xf0 <= first <= 0xf4 else 0
        if width and lead < index < lead + width:
            try: data[lead:lead + width].decode('utf-8')
            except UnicodeDecodeError: continue
            index = lead + width; start = position + index; break
    raw = data[index:]
    return raw, {'source': 'original-output-log', 'state': 'observed', 'requestedTailBytes': count,
        'startOffset': start, 'nextOffset': start + len(raw), 'pageBytes': len(raw), 'totalBytes': before.st_size,
        'omittedPrefixBytes': start, 'boundarySkippedBytes': start - requested,
        'observedBytesAfterRead': after.st_size, 'changedDuringRead': (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns),
        'sha256': hashlib.sha256(raw).hexdigest()}


def preview(path, job):
    if job.get('kind') != 'build' or job.get('state') != 'failed': return None
    raw, tail = read(path, MAX_TAIL)
    found = ERROR.search(raw)
    begin = found.start() if found else max(0, len(raw) - 2048)
    excerpt = raw[begin:begin + 2048]
    try: text = excerpt.decode('utf-8'); encoding = 'utf-8'
    except UnicodeDecodeError: text = excerpt.decode('utf-8', errors='replace'); encoding = 'replacement'
    text = ANSI.sub('', text); full_display = text
    while len(json.dumps(text, ensure_ascii=False).encode()) > 2400: text = text[:max(1,len(text)//2)]
    return {**tail, 'kind': 'build-log-excerpt', 'jobRevision': job['revision'],
        'startOffset': tail['startOffset'] + begin, 'nextOffset': tail['startOffset'] + begin + len(excerpt),
        'pageBytes': len(excerpt), 'sha256': hashlib.sha256(excerpt).hexdigest(), 'text': text, 'displayTruncated': text != full_display,
        'encoding': encoding, 'ansiRemoved': True, 'consumesCursor': False, 'excerptOnly': True,
        'captureLimitReached': tail['totalBytes'] >= LIMITS['outputBytes'], 'captureTruncated': job.get('captureTruncated'),
        'read': {'jobId': job['id'], 'view': 'tail', 'tailBytes': MAX_TAIL},
        'notice': 'Bounded original-log excerpt, not a complete error list or native build proof. Inspect project source diagnostics separately from SDK inventory or host failures. Read the tail and original output offsets for context; no build was repeated.'}
