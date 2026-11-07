"""Qualify complete historical patch-failure observations, never patch success."""
import hashlib
import json
import re

from session_store import encode


def confirmed(tool):
    if (tool['tool'] != 'studio_apply_patch' or tool['state'] != 'failed'
            or tool['run_busy'] or tool['run_state'] not in ('completed','failed','interrupted')
            or not tool['intent'] or len(tool['intent'].encode()) > 131072
            or not tool['worker'] or len(tool['worker'].encode()) > 32768):
        return None
    worker=json.loads(tool['worker']);end=worker.get('processEnd') or {};unit=end.get('unit') or {}
    if (end.get('confirmed') is not True or end.get('replayed') is not False
            or end.get('observedBy') != 'original-unit-and-process-end'
            or unit.get('ActiveState') not in ('inactive','failed') or unit.get('MainPID') != '0'):
        return None
    args=json.loads(tool['intent']);result=json.loads(tool['result'])
    if (not isinstance(args,dict) or set(args) != {'patch','expectedHashes'}
            or not isinstance(args['patch'],str) or not isinstance(args['expectedHashes'],dict)
            or hashlib.sha256(encode({'tool':tool['tool'],'arguments':args}).encode()).hexdigest() != tool['arguments_hash']
            or not isinstance(result,dict) or set(result) != {'success','error','partialChangesPossible','output','files'}
            or result['success'] is not False or result['error'] != 'patchFailed'
            or result['partialChangesPossible'] is not True or not isinstance(result['output'],str)
            or len(result['output']) > 24000 or not isinstance(result['files'],dict)):
        return None
    lines=args['patch'].strip().splitlines()
    if not lines or lines[0] != '*** Begin Patch' or lines[-1] != '*** End Patch':return None
    from file_worker import parts,Fault
    targets=[];old=set()
    try:
        for line in lines:
            for prefix,existing in (('*** Add File: ',False),('*** Delete File: ',True),('*** Update File: ',True),('*** Move to: ',False)):
                if not line.startswith(prefix):continue
                path=line[len(prefix):]
                if not parts(path):return None
                targets.append(path)
                if existing:old.add(path)
    except Fault:return None
    if not 1 <= len(targets) <= 64 or set(result['files']) != set(targets) or set(args['expectedHashes'])-set(targets):return None
    valid=lambda value:isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
    if any(not valid(args['expectedHashes'].get(path)) for path in old):return None
    if any(value is not None and not valid(value) for value in args['expectedHashes'].values()):return None
    if any(value is not None and not valid(value) for value in result['files'].values()):return None
    return {'schema':1,'kind':'terminal-patch-observation','readOnly':True,'toolReceiptId':tool['call_id'],
        'argumentsSha256':tool['arguments_hash'],'resultSha256':hashlib.sha256(encode(result).encode()).hexdigest(),
        'processEndConfirmed':True,'patchSucceeded':False,'partialChangesPossible':True,
        'postPatchFiles':result['files'],
        'changedFiles':[path for path,value in result['files'].items() if args['expectedHashes'].get(path) != value],
        'currentFilesVerified':False}
