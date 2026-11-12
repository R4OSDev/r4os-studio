"""Qualify complete historical patch-failure observations, never patch success."""
import hashlib
import json
import re

from session_store import encode
from tool_receipt_boundary import fingerprint


def valid_sha(value):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None


def bound_hashes(db, tool, proofs, targets, old):
    if db is None or not isinstance(proofs,dict) or set(proofs) != targets: return None
    hashes = {}
    for path, proof in proofs.items():
        if not isinstance(proof,dict) or set(proof) != {'path','sha256','sourceCallId'}: return None
        target, checksum, source = proof['path'], proof['sha256'], proof['sourceCallId']
        if not isinstance(target,str) or not target.startswith('/'): return None
        if path in old:
            if not valid_sha(checksum) or not isinstance(source,str): return None
            version = db.execute("""SELECT version.value FROM tools t, json_each(t.result,'$._fileVersions') version
                WHERE t.run_id=? AND t.call_id=? AND t.rowid<? AND t.state='completed' AND json_extract(t.result,'$.success')=1
                AND t.tool IN ('studio_read_file','studio_write_file','studio_apply_patch') AND version.key=?""",
                (tool['run_id'],source,tool['receipt_rowid'],target)).fetchone()
            if version is None or version[0] != checksum: return None
        elif checksum is not None or source is not None:
            return None
        hashes[path] = checksum
    return hashes


def confirmed(tool, db=None):
    if (tool['tool'] != 'studio_apply_patch' or tool['state'] != 'failed'
            or tool['run_busy'] or tool['run_state'] not in ('completed','failed','interrupted')
            or not tool['intent'] or len(tool['intent'].encode()) > 524288
            or not tool['worker'] or len(tool['worker'].encode()) > 32768):
        return None
    worker=json.loads(tool['worker']);end=worker.get('processEnd') or {};unit=end.get('unit') or {}
    if (end.get('confirmed') is not True or end.get('replayed') is not False
            or end.get('observedBy') != 'original-unit-and-process-end'
            or unit.get('ActiveState') not in ('inactive','failed') or unit.get('MainPID') != '0'):
        return None
    args=json.loads(tool['intent']);result=json.loads(tool['result'])
    if not isinstance(args,dict): return None
    automatic = '_fileWriteBasis' in args
    proofs = args.pop('_fileWriteBasis',None)
    if (set(args) != ({'patch'} if automatic else {'patch','expectedHashes'})
            or not isinstance(args['patch'],str) or len(encode(args).encode()) > 131072
            or fingerprint(tool['tool'],args) != tool['arguments_hash']
            or not isinstance(result,dict) or set(result) != {'success','error','partialChangesPossible','output','files'}
            or result['success'] is not False or result['error'] != 'patchFailed'
            or result['partialChangesPossible'] is not True or not isinstance(result['output'],str)
            or len(result['output']) > 24000 or not isinstance(result['files'],dict)):
        return None
    from file_worker import parts,patch_targets,Fault
    try:
        entries=patch_targets(args['patch'])
        if any(not parts(path) for path,_ in entries): return None
    except Fault:return None
    targets={path for path,_ in entries};old={path for path,role in entries if role=='old'}
    hashes=bound_hashes(db,tool,proofs,targets,old) if automatic else args['expectedHashes']
    if not isinstance(hashes,dict) or set(result['files']) != targets or set(hashes)-targets:return None
    if any(not valid_sha(hashes.get(path)) for path in old):return None
    if any(value is not None and not valid_sha(value) for value in hashes.values()):return None
    if any(value is not None and not valid_sha(value) for value in result['files'].values()):return None
    return {'schema':1,'kind':'terminal-patch-observation','readOnly':True,'toolReceiptId':tool['call_id'],
        'argumentsSha256':tool['arguments_hash'],'resultSha256':hashlib.sha256(encode(result).encode()).hexdigest(),
        'processEndConfirmed':True,'patchSucceeded':False,'partialChangesPossible':True,
        'postPatchFiles':result['files'],
        'changedFiles':[path for path,value in result['files'].items() if hashes.get(path) != value],
        'currentFilesVerified':False}
