"""Private, bounded Studio GOAL authority; never a native Codex Goal projection.

Only an accepted original Play can create a ledger. Reading/recovering it never
starts a process. Public Claude GOAL controls remain gated until their separate
session/control integration is qualified.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from attachment_store import birth
from goal_contract import objective
from run_store import get_run
from session_store import encode, identity, now
from store import ProjectFault

MAX_STEPS = 8
MAX_ACTIVE_SECONDS = 900
CONTINUE_TEXT = ('Continue the original saved Studio GOAL within its unchanged scope and permissions. '
                 'Inspect original receipts before acting; never repeat an unconfirmed effect. '
                 'Before ending this step, call mcp__studio__report_goal with continue, complete or blocked and a concise reason.')
REPORT_TOOL = {'name': 'report_goal', 'description':
    'Report progress on the original bounded Studio GOAL. This reports a status; it grants no new scope or permissions. '
    'Use complete only after the original objective and required checks are satisfied. Use blocked when user input or an external change is required. '
    'Use continue when useful authorized work remains. Report once per step before ending the response. '
    'The host independently checks the original Play, input receipt, native result, tool receipts and execution bounds.',
    'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['status', 'reason'],
        'properties': {'status': {'type': 'string', 'enum': ['continue', 'complete', 'blocked']},
                       'reason': {'type': 'string', 'minLength': 1, 'maxLength': 2000}}}}


def digest(value): return hashlib.sha256(encode(value).encode()).hexdigest()
def text_hash(value): return hashlib.sha256(value.encode()).hexdigest()
def boot(): return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def exists(store):
    return store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_goal_executions'").fetchone() is not None


def freeze(store, sid, command):
    """Internal capture boundary. The public Goals.accept still rejects Claude."""
    data = json.loads(command['payload']); saved = data.get('_goal') or {}
    runtime = store.get(sid)['engine'].get('claude') or {}
    if (command['session_id'] != sid or command['state'] != 'pending' or data.get('action') != 'play'
            or saved.get('source') != 'studio-claude' or saved.get('nativeSessionId') != runtime.get('nativeSessionId')
            or data.get('sessionRevision') != store.row(sid)['revision'] or data.get('target')):
        raise ProjectFault('This bounded Claude execution has no original accepted Studio Play.', 409)
    text = objective(saved.get('objective'))
    return {'schema': 1, 'source': 'studio-claude', 'executionId': identity(command['request_id']),
        'requestId': command['request_id'], 'objective': text, 'objectiveSha256': text_hash(text),
        'commandFingerprint': command['fingerprint'], 'nativeSessionId': runtime['nativeSessionId'],
        'maxSteps': MAX_STEPS, 'maxActiveSeconds': MAX_ACTIVE_SECONDS}


def lost(store, run_id):
    """Passive recovery only. No continuation, prompt, clock reset or replay."""
    if not exists(store): return
    for row in store.db.execute('SELECT * FROM claude_goal_executions WHERE run_id=?', (run_id,)).fetchall():
        value = json.loads(row['payload'])
        if value['state'] in ('complete', 'blocked', 'budgetLimited', 'paused', 'unknown'): continue
        value.update(state='unknown', reason='The original bounded Claude worker ended without a confirmed closure. Nothing was restarted.', updatedAt=now())
        with store.db: store.db.execute('UPDATE claude_goal_executions SET payload=? WHERE execution_id=?', (encode(value), row['execution_id']))


class GoalJournal:
    def __init__(self, worker, monotonic=time.monotonic_ns):
        self.w = worker; self.spec = worker.config['claudeGoalExecution']; self.monotonic = monotonic
        self.binding = {'owner': {'type': worker.store.owner_type, 'id': worker.store.owner_id},
            'sessionId': worker.session_id, 'runId': worker.run_id, 'requestId': worker.row['request_id'],
            'configSha256': digest(worker.config), 'worker': worker.credential_worker,
            'nativeSessionId': worker.config['engine']['claude']['nativeSessionId']}

    def start(self):
        from goal_store import Goals
        original = Goals(self.w.store).command(self.w.session_id, self.spec['requestId'])
        if freeze(self.w.store, self.w.session_id, original) != self.spec or self.binding['requestId'] != self.spec['requestId']:
            raise ProjectFault('The original Claude Play contract changed. It was not restarted.', 409)
        db = self.w.store.db
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS claude_goal_executions(
                execution_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),
                run_id TEXT NOT NULL,payload TEXT NOT NULL)''')
            if db.execute('SELECT 1 FROM claude_goal_executions WHERE execution_id=?', (self.spec['executionId'],)).fetchone():
                raise ProjectFault('This original Claude Play already has an execution ledger. Inspect it; it was not replayed.', 409)
            record = {'schema': 1, 'source': 'studio-claude', 'binding': self.binding, 'contract': self.spec,
                'state': 'admitting', 'steps': [], 'startedNs': None, 'bootId': boot(), 'createdAt': now(), 'updatedAt': now(), 'reason': None}
            record['steps'].append(self.new_step(1, self.spec['requestId'], 'human', self.spec['objective']))
            db.execute('INSERT INTO claude_goal_executions VALUES (?,?,?,?)',
                (self.spec['executionId'], self.w.session_id, self.w.run_id, encode(record)))

    def new_step(self, number, request, origin, text):
        return {'ordinal': number, 'inputId': request, 'origin': origin, 'textSha256': text_hash(text),
            'state': 'admitting', 'admissionId': None, 'submitted': False, 'inputReceipt': None,
            'report': None, 'reportCallId': None, 'nativeResult': None}

    def read(self, live=True):
        row = self.w.store.db.execute('SELECT payload FROM claude_goal_executions WHERE execution_id=?', (self.spec['executionId'],)).fetchone()
        if not row: raise ProjectFault('The original Claude Play ledger is missing.', 409)
        value = json.loads(row[0]); run = get_run(self.w.store, self.w.run_id)
        command = self.w.store.db.execute('SELECT state,fingerprint FROM goal_commands WHERE request_id=? AND session_id=?',
            (self.spec['requestId'], self.w.session_id)).fetchone()
        if (value['binding'] != self.binding or value['contract'] != self.spec
                or digest(json.loads(run['config'])) != self.binding['configSha256']
                or json.loads(run['worker'] or '{}') != self.binding['worker']
                or value['bootId'] != boot() or self.w.store.get(self.w.session_id)['engine']['claude'] != self.w.config['engine']['claude']
                or not command or command['state'] not in ('pending','confirmed') or command['fingerprint'] != self.spec['commandFingerprint']):
            raise ProjectFault('The original Claude Play binding changed. Its ledger was preserved.', 409)
        if live and (not run['busy'] or self.binding['worker']['pid'] != os.getpid()
                or birth(os.getpid()) != self.binding['worker']['birth']):
            raise ProjectFault('The original Claude Play worker is no longer active.', 409)
        return value

    def save(self, value):
        value['updatedAt'] = now()
        self.w.store.db.execute('UPDATE claude_goal_executions SET payload=? WHERE execution_id=?', (encode(value), self.spec['executionId']))

    def admitted(self, admission):
        value = self.read(); step = value['steps'][-1]
        if value['state'] != 'admitting' or step['state'] != 'admitting' or step['admissionId'] is not None or self.w.stopping:
            raise ProjectFault('This original Claude GOAL step cannot acquire another input admission.', 409)
        step['admissionId'] = identity(admission['admissionId'])
        with self.w.store.db: self.save(value)

    def submitted(self, request):
        value = self.read(); step = value['steps'][-1]
        if request != step['inputId'] or not step['admissionId']:
            raise ProjectFault('The original Claude GOAL input was not admitted.', 409)
        step['submitted'] = True
        with self.w.store.db: self.save(value)

    def acknowledge(self, frame):
        reported = frame.get('identity', {}); native = frame.get('native', {})
        if reported.get('nativeType') not in ('user', 'assistant', 'stream_event', 'result') or not reported.get('nativeInputRequestIds'): return False
        value = self.read(); step = value['steps'][-1]
        if (reported.get('studioRequestId') != self.spec['requestId'] or reported.get('studioGoalStepId') != step['inputId']
                or reported.get('nativeInputRequestIds') != [step['inputId']]
                or reported.get('nativeSessionId') != self.binding['nativeSessionId']
                or native.get('session_id') != self.binding['nativeSessionId'] or native.get('type') != reported.get('nativeType')
                or not (reported.get('nativeMessageId') or reported.get('providerMessageId')) or not step['admissionId']
                or step['state'] not in ('admitting', 'active') or value['state'] not in ('admitting','running','stopping')):
            raise ProjectFault('The native Claude GOAL input receipt is not bound to its original step.', 409)
        if native['type'] == 'user' and (native.get('isReplay') is not True or reported.get('nativeInputReceiptKind') != 'stdinEcho'
                or reported.get('nativeInputTextSha256') != step['textSha256']):
            raise ProjectFault('The native Claude GOAL input echo differs from the original step.', 409)
        if not step['inputReceipt']:
            step.update(state='active', submitted=True, inputReceipt={k: reported.get(k) for k in
                ('nativeMessageId', 'providerMessageId', 'nativeInputReceiptKind', 'nativeInputTextSha256')})
            if value['startedNs'] is None: value['startedNs'] = self.monotonic()
            if value['state'] != 'stopping': value['state'] = 'running'
            with self.w.store.db: self.save(value)
        return True

    def report(self, arguments, call_id, admission_error=None):
        db = self.w.store.db
        if not isinstance(call_id,str) or not 1<=len(call_id.encode())<=256 or any(ord(c)<=32 or ord(c)==127 for c in call_id):
            return {'success':False,'error':'invalidCall','output':'The original native GOAL report call ID is required.'}
        if (not isinstance(arguments, dict) or set(arguments) != {'status', 'reason'}
                or arguments.get('status') not in ('continue', 'complete', 'blocked')
                or not isinstance(arguments.get('reason'), str) or not arguments['reason'].strip()
                or len(arguments['reason']) > 2000 or any(c == '\x00' or 0xD800 <= ord(c) <= 0xDFFF for c in arguments['reason'])):
            return {'success': False, 'error': 'invalidArguments', 'output': 'Report one bounded GOAL status and a reason of at most 2000 characters.'}
        hashed = digest({'tool': 'studio_report_goal', 'arguments': arguments})
        previous = db.execute('SELECT t.* FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.call_id=? LIMIT 1',
            (self.w.session_id, call_id)).fetchone()
        if previous:
            if previous['arguments_hash'] != hashed or not previous['result']:
                return {'success': False, 'error': 'conflict', 'output': 'The original GOAL report call has another binding. It was not repeated.'}
            return json.loads(previous['result'])
        value = self.read(); step = value['steps'][-1]
        if admission_error is not None:result=admission_error
        elif self.w.stopping or value['state'] != 'running' or step['state'] != 'active' or not step['inputReceipt'] or step['report']:
            result={'success': False, 'error': 'unavailable', 'output': 'This original GOAL step cannot accept another progress report.'}
        else:
            result = {'success': True, 'output': 'The bounded GOAL report was recorded. Only the host may authorize another step.',
                'studioGoal': {'executionId': self.spec['executionId'], 'inputId': step['inputId'], 'status': arguments['status']}}
            step.update(report=arguments, reportCallId=call_id)
        with db:
            db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,?)',
                (self.w.run_id, call_id, 'studio_report_goal', hashed, 'completed' if result['success'] else 'failed', encode(arguments), encode(result)))
            self.save(value)
        return result

    def result(self, native):
        value = self.read(); step = value['steps'][-1]
        native_id = native.get('uuid')
        identity(native_id)
        if (native.get('type') != 'result' or native.get('session_id') != self.binding['nativeSessionId']
                or not isinstance(native_id, str) or not native_id or len(native_id) > 256
                or value['state'] not in ('admitting','running','stopping')
                or step['state'] not in ('admitting', 'active')
                or any(s['nativeResult'] and s['nativeResult']['id'] == native_id for s in value['steps'])):
            raise ProjectFault('The native Claude GOAL result has a foreign or duplicate step identity.', 409)
        step['nativeResult'] = {'id': native_id, 'subtype': native.get('subtype'), 'isError': native.get('is_error') is True}
        step['state'] = 'resultConfirmed'
        unsafe = (not step['inputReceipt'] or self.w.uncertain_effect
            or self.w.store.db.execute("""SELECT 1 FROM tools WHERE run_id=? AND
                (result IS NULL OR state IN ('intent','unknown') OR json_extract(result,'$.partialChangesPossible')=1
                 OR json_extract(result,'$.error')='unknown')""", (self.w.run_id,)).fetchone())
        if unsafe:
            value.update(state='closing', terminalStatus='unknown', reason='The original GOAL input or tool outcome is unconfirmed. No continuation was authorized.')
        elif self.w.stopping or value['state'] == 'stopping':
            value.update(state='closing', terminalStatus=value.get('terminalStatus', 'paused'))
        elif native.get('subtype') != 'success' or native.get('is_error'):
            value.update(state='closing', terminalStatus='blocked', reason='The original native Claude GOAL step ended with an error. No automatic retry was authorized.')
        elif not step['report']:
            value.update(state='closing', terminalStatus='blocked', reason='The original Claude step has no confirmed GOAL progress report. Play explicitly after review.')
        elif step['report']['status'] != 'continue':
            value.update(state='closing', terminalStatus=step['report']['status'], reason=step['report']['reason'])
        elif len(value['steps']) >= self.spec['maxSteps'] or self.expired(value):
            value.update(state='closing', terminalStatus='budgetLimited', reason='This Play reached its bounded step or active-time limit. Review before pressing Play again.')
        else:
            value.update(state='between', reason=step['report']['reason'])
        with self.w.store.db: self.save(value)
        return value['state'] == 'between'

    def expired(self, value=None):
        value = value or self.read()
        return value['startedNs'] is not None and self.monotonic() - value['startedNs'] >= self.spec['maxActiveSeconds'] * 1000000000

    def next(self):
        value = self.read()
        if self.w.stopping or value['state'] != 'between' or value['steps'][-1]['state'] != 'resultConfirmed':
            raise ProjectFault('The original Claude GOAL continuation is not authorized.', 409)
        if len(value['steps']) >= self.spec['maxSteps'] or self.expired(value):
            self.stop('This Play reached its bounded step or active-time limit.', 'budgetLimited'); return None
        request = str(uuid.uuid4()); value['steps'].append(self.new_step(len(value['steps']) + 1, request, 'auto-continuation', CONTINUE_TEXT))
        value['state'] = 'admitting'
        with self.w.store.db: self.save(value)
        return request

    def stop(self, reason='The user paused or stopped this bounded GOAL.', status='paused'):
        if status not in ('paused', 'budgetLimited'): raise ValueError('Invalid bounded GOAL stop status.')
        value = self.read()
        if value['state'] in ('complete', 'blocked', 'budgetLimited', 'paused', 'unknown'): return
        value.update(state='stopping', terminalStatus=status, reason=reason)
        with self.w.store.db: self.save(value)

    def finish(self, confirmed, no_input=False):
        value = self.read(); step = value['steps'][-1]
        if value['state'] in ('complete','blocked','budgetLimited','paused','unknown'):return value
        if (confirmed and value['state']=='closing' and not self.w.uncertain_effect and step['state'] == 'resultConfirmed'
                and step['inputReceipt'] and value.get('terminalStatus')):
            value['state'] = value['terminalStatus']
        elif confirmed and value['state'] in ('admitting','stopping') and no_input and not step['submitted'] and not step['inputReceipt']:
            value.update(state='paused' if self.w.stopping else 'blocked', reason='No input was submitted for this original step. Review before pressing Play again.')
        else:
            value.update(state='unknown', reason='The original bounded GOAL closure is unconfirmed. Nothing will be replayed automatically.')
        with self.w.store.db: self.save(value)
        return value
