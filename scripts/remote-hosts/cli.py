#!/usr/bin/env python3
"""Fixed local metadata adapter; no commands, network or secrets in responses."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from catalog import operation, CatalogFault


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384: raise CatalogFault('Remote Host request is too large.', 413)
    result = operation(Path(sys.argv[1]), json.loads(raw))
    print(json.dumps({'result': result}, ensure_ascii=True))


if __name__ == '__main__':
    try: main()
    except CatalogFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except sqlite3.IntegrityError:
        print(json.dumps({'error': 'The host name is already in use, or its stored binding conflicts.', 'code': 409})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Remote Host storage is unavailable. Preserve existing data and reconcile the original request.', 'code': 503})); sys.exit(1)
