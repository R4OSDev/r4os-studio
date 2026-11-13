"""Reuse a full REA verification for the same local installation and file state."""

import fcntl
import hashlib
import os
from pathlib import Path
import stat

from skill_mcp_client import McpFault, atomic, directory, encoded, strict


def verify(cache, spec, manifest_hash, root, files, *, manifest_state):
    # Scope the receipt to this boot, installation and verification code.
    identity = {
        'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'root': str(root),
        'manifest': manifest_hash,
        'verifier': hashlib.sha256(Path(spec.__file__).read_bytes()).hexdigest(),
    }
    key = hashlib.sha256(os.fsencode(root)).hexdigest()
    try:
        cache = directory(cache)
    except (OSError, McpFault):
        spec.verify_files(root, files, manifest_state=manifest_state)
        return
    receipt = cache / (key + '.json')
    try:
        fd = os.open(cache / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        spec.verify_files(root, files, manifest_state=manifest_state)
        return
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            spec.verify_files(root, files, manifest_state=manifest_state)
            return
        fcntl.flock(fd, fcntl.LOCK_EX)
        previous = None
        try:
            saved = strict(spec.read(receipt, 64 * 1024 * 1024))
            if saved['identity'] == identity:
                previous = {name: tuple(values) for name, values in saved['files'].items()}
        except (OSError, KeyError, TypeError, ValueError, AttributeError):
            pass
        result = spec.verify_files(root, files, manifest_state=manifest_state, previous=previous)
        if result is not previous:
            try:
                atomic(receipt, encoded({'identity': identity, 'files': result}))
            except OSError:
                pass
    finally:
        os.close(fd)
