"""Original own-window delegation, immutable commands and native frame receipts."""
import asyncio
import json
import re
import sqlite3
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from jobs import now
from layout import save


def enabled(store, job):
    from authorization import permits
    if not job.get('agentRunId') or job.get('windowControlRequested') is not True: return False
    path = store.projects / store.id / 'Sessions/Sessions.sqlite'
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid window permission storage.')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        row = connection.execute('SELECT session_id,config FROM runs WHERE id=?', (job['agentRunId'],)).fetchone()
    finally: connection.close()
    if not row or row[0] != job.get('sessionId'): return False
    config = json.loads(row[1])
    return permits(config, store.id, 'control_app_window', 'run_project')


def validate(value):
    if not isinstance(value, dict) or value.get('action') not in ('resize', 'minimize', 'restore', 'status'):
        raise DevelopmentFault('Choose resize, minimize, restore or status for the own app window.', 400)
    action = value['action']
    keys = {'action', 'width', 'height'} if action == 'resize' else {'action'}
    if action == 'status' and 'operationId' in value: keys.add('operationId')
    if set(value) != keys: raise DevelopmentFault('Unexpected own window fields.', 400)
    if action == 'resize' and any(type(value[k]) is not int or not 64 <= value[k] <= limit for k, limit in (('width',1280),('height',1024))):
        raise DevelopmentFault('Window client dimensions must be 64..1280 by 64..1024.', 400)
    if action == 'status' and (not isinstance(value.get('operationId','0'), str) or not re.fullmatch(r'[0-9]{1,20}',value.get('operationId','0')) or int(value.get('operationId','0')) > 18446744073709551615):
        raise DevelopmentFault('Use the original lossless window operation ID.', 400)
    return action


def public(value, request_id=None):
    result = {k: value[k] for k in ('result','phase','frameReady','operationId','deadline','kind','appliedTick') if k in value}
    for key in ('applied','current'):
        if isinstance(value.get(key), dict): result[key] = {k:v for k,v in value[key].items() if k != 'identity'}
    if request_id: result['requestId'] = request_id
    result['appliedConfirmed'] = value.get('phase') == 3 and value.get('result') == 0
    result['confirmed'] = result['appliedConfirmed'] and value.get('frameReady') is True
    result['terminalRejected'] = value.get('phase') == 4 and type(value.get('result')) is int and value['result'] < 0
    result['pending'] = not (result['confirmed'] or result['terminalRejected']) and value.get('operationId') not in (None,'0')
    return result


def next_operation(job):
    # WINSVC rejects any operation below the previous one on this grant.
    # UUID-derived request IDs are idempotency keys, not ordered native IDs.
    values = [(job.get('windowControl') or {}).get('operationId'), job.get('windowOperationCounter', '0')]
    if any(not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value) for value in values):
        raise DevelopmentFault('The original window operation counter is unavailable. No command was prepared.')
    previous = max(int(value) for value in values)
    if previous >= 18446744073709551615:
        raise DevelopmentFault('The original window operation counter is exhausted. No command was prepared.')
    return str(previous + 1)


async def bind(execution, launch, state):
    from desktop_evidence import prepare
    original = launch.evidence_launch
    available = original and original.get('control_requested') is True and original.get('evidence_scope_available') is True
    record = {'version':1,'available':False,'reason':'The original launch has no confirmed native window delegation.'}
    if not available:
        execution.store.update(execution.job['id'], windowControl=record)
        return state
    scope = prepare(original)
    intent = {'schema':1,'jobId':execution.job['id'],'launch':original,'scope':scope,'createdAt':now()}
    save(execution.work/'window-control-intent.json',intent)
    if state.get('state') != 'running' or state.get('closeConfirmed'):
        execution.store.update(execution.job['id'], windowControl={**record,'reason':'The own app already ended.'})
        return state
    try:
        result = await execution.control.call('window_bind', evidenceToken=scope, windowGrant=original['control_grant'])
    except DevelopmentFault as error:
        # Read-only binding cannot invalidate a successful fast app completion.
        execution.store.update(execution.job['id'], windowControl={**record,'reason':str(error)})
        return state
    save(execution.work/'window-control.json',{**intent,'native':result})
    if result.get('result') == 0 and result.get('phase') == 1 and result.get('token'):
        record = {'version':1,'available':True,'operationId':'0','native':public(result)}
    else:
        record = {**record,'reason':'The assigned guest did not confirm the original controller/window incarnation.','native':public(result)}
    execution.store.update(execution.job['id'],windowControl=record)
    state = await execution.control.call('poll'); execution.output(state)
    return {**state,'outputBase64':''}


async def perform(execution, job, message, state, control, lease, authorization):
    from authorization import authorize, permits
    from vm_worker import guard
    from actions import finish
    if not permits(authorization, execution.store.id, 'control_app_window', 'run_project'):
        raise DevelopmentFault('Own window control requires its explicit session permission.',403)
    if not (job.get('windowControl') or {}).get('available'):
        raise DevelopmentFault((job.get('windowControl') or {}).get('reason') or 'Deploy and run with the window-control-v1 helper and controller delegation first.')
    if state.get('state') != 'running' or state.get('closeConfirmed'):
        raise DevelopmentFault('The own Desktop app already ended.')
    value = message['input']; action = validate(value); request_id = message['requestId']
    if action == 'status':
        operation = str(int(value.get('operationId',(job.get('windowControl') or {}).get('operationId','0'))))
    else:
        operation = next_operation(job)
        # Reserve before preparation, so even a rejected/failed preparation
        # cannot reuse an ID or let a status read rewind the next command.
        execution.store.update(job['id'], windowOperationCounter=operation)
        prepared = await control.call('window_prepare',windowOperation=operation,windowKind=action,
            windowWidth=value.get('width',0),windowHeight=value.get('height',0))
        if not isinstance(prepared.get('nativeRequest'),str): raise DevelopmentFault('The own native window request could not be prepared.')
        # The native deadline, complete token/incarnation, exact kind/geometry
        # and operation are durable before the one mutating command.
        save(execution.work/('window-'+request_id+'.intent.json'),{'schema':1,'jobId':job['id'],'executionId':job['executionId'],
            'target':job['target'],'process':job['process'],'operationId':operation,'input':value,'nativeRequest':prepared['nativeRequest'],'createdAt':now()})
        guard(execution.store,job,lease)
        authorize(execution.store,message['owner'],'window',message['peerPid'],execution.store.get(job['id']))
        result = await control.call('window_command',nativeRequest=prepared['nativeRequest'])
        if 'transportError' in result:
            result = await control.call('window_status',windowOperation=operation)
    if action == 'status': result = await control.call('window_status',windowOperation=operation)
    # Reconcile only the immutable original command and its fresh composed view.
    for _ in range(12):
        if 'transportError' in result: break
        if result.get('phase') not in (2,3) or result.get('frameReady') is True: break
        await asyncio.sleep(.1)
        guard(execution.store,job,lease)
        result = await control.call('window_status',windowOperation=operation)
    save(execution.work/('window-'+request_id+'.receipt.json'),{'operationId':operation,'native':result,'observedAt':now()})
    if 'transportError' in result:
        raise UnconfirmedGuestEffect('The original window operation is unconfirmed. Query its operationId; no command was replayed.')
    if result.get('operationId') != operation:
        if result.get('operationId') == '0' and result.get('result') == -1:
            raise UnconfirmedGuestEffect('The native broker has no matching receipt for original window operation ' + operation + '. No command was replayed.')
        raise UnconfirmedGuestEffect('The window receipt names another operation. No command was replayed.')
    value = public(result,request_id)
    if action == 'status': value['confirmed'] = result.get('result') == 0
    if not value['confirmed']:
        value['reason'] = ('The original window operation was rejected. Its rejection is final; use a fresh own frame for further input.'
            if value['terminalRejected'] else 'The original window operation was applied; its fresh composed frame is not confirmed.'
            if value['appliedConfirmed'] else 'The native window operation is pending, rejected, expired or unavailable; inspect its original receipt.')
    execution.store.update(job['id'],windowControl={'version':1,'available':True,'operationId':operation,'native':value})
    if action != 'status' and result.get('phase') in (2,8):
        raise UnconfirmedGuestEffect('Original window operation ' + operation + ' remains unconfirmed. Read its status without another command.')
    if value['terminalRejected']:
        # This is a fresh scope read, not a replacement operation receipt.
        # Keep the immutable rejection above and qualify only the same own view.
        view = await control.call('window_status', windowOperation='0')
        save(execution.work/('window-'+request_id+'.view.json'),
            {'operationId': operation, 'statusOnly': True, 'native': view, 'observedAt': now()})
    state = await control.call('poll'); execution.output(state); state['outputBase64']=''
    finish(execution.store,request_id,value)
    return state,value


async def release(execution, control):
    if not (execution.store.get(execution.job['id']).get('windowControl') or {}).get('available'): return
    save(execution.work/'window-release-intent.json',{'jobId':execution.job['id'],'createdAt':now()})
    result = await control.call('window_release')
    save(execution.work/'window-release.json',result)
