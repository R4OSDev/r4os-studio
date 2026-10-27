#!/usr/bin/env python3
"""Verified UTF-8 download: bounded JSON header, then raw bytes with backpressure."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects'))
from store import ProjectFault
from storage import connection
from exports import open_archive

started = False


def main():
    global started
    os.umask(0o077)
    projects, project_id, export_id = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    with connection(projects, project_id) as db:
        if db is None:
            raise ProjectFault('This roadmap is unavailable.', 404)
        with open_archive(projects, project_id, export_id) as (info, stream):
            sys.stdout.buffer.write((json.dumps({'result': info}) + '\n').encode())
            sys.stdout.buffer.flush()
            started = True
            while block := stream.read(65536):
                sys.stdout.buffer.write(block)
            sys.stdout.buffer.flush()


if __name__ == '__main__':
    try:
        main()
    except ProjectFault as error:
        if not started:
            print(json.dumps({'error': str(error), 'code': error.code}), flush=True)
        sys.exit(1)
    except Exception:
        # An incomplete HTTP body never satisfies its declared Content-Length.
        sys.exit(1)
