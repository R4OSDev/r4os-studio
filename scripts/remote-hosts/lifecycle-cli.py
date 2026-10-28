#!/usr/bin/env python3
"""Explicit offline restore maintenance as the data owner; no network or retry."""
import json
from pathlib import Path
import sys
from catalog import CatalogFault, fields
import lifecycle


def main():
    raw = sys.stdin.buffer.read(4097)
    if len(raw) > 4096: raise CatalogFault('The maintenance request exceeds its limit.', 413)
    value = json.loads(raw); fields(value, ['operation', 'projectId', 'hostId', 'jobId'], ['input'])
    projects = Path(sys.argv[1]).absolute()
    if value['operation'] == 'read': fields(value, ['operation', 'projectId', 'hostId', 'jobId']); return lifecycle.details(projects, value['projectId'], value['hostId'], value['jobId'])
    if value['operation'] == 'review': fields(value, ['operation', 'projectId', 'hostId', 'jobId', 'input']); return lifecycle.review(projects, value['projectId'], value['hostId'], value['jobId'], value['input'])
    raise CatalogFault('Only reading or explicitly acknowledging an original unknown result is supported.', 400)


if __name__ == '__main__':
    try: print(json.dumps({'result': main()}, ensure_ascii=True))
    except CatalogFault as error: print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception: print(json.dumps({'error': 'The original remote history needs maintenance. No remote action was performed.', 'code': 503})); sys.exit(1)
