"""Original-Play evidence and native status-only Goal continuation.

The shared ProviderRetry owns the timer and durable claim. This adapter cannot
create a replacement worker, change a Goal objective or reset native accounting.
Only complete current native evidence can exclude a model-issued Goal block.
"""
import asyncio
import json
from pathlib import Path

from goal_contract import native_goal
from goal_retry_evidence import RUNTIME_VERSION, RUNTIME_SHA256, Scope, digest, goal_binding, inspect_original
from goal_store import Goals


class GoalRetry:
    def __init__(self, retry):
        self.retry = retry
        self.w = retry.w
        self.active_turn = None
        self.blocked = None
        self.evidence = None
        self.started = asyncio.Event()

    def active_execution(self):
        goal = self.w.goal_worker
        return bool(goal and goal.armed and not goal.dormant and goal.activation)

    def controls(self):
        row = self.w.store.db.execute(
            'SELECT count(*),max(rowid) FROM goal_commands WHERE session_id=?',
            (self.w.session_id,)).fetchone()
        return list(row)

    def native(self, value):
        goal = native_goal(value, self.w.thread_id)
        if goal is None:
            raise ValueError('The original native Goal is missing')
        goal.setdefault('tokenBudget', None)
        return goal

    def capture_active(self, turn_id, value):
        if not self.active_execution() or not value:
            return
        goal = self.native(value)
        if goal['status'] != 'active':
            return
        self.active_turn = {
            'turnId': turn_id, 'goalBindingSha256': goal_binding(goal),
            'activationSha256': digest(self.w.goal_worker.activation),
            'controls': self.controls(),
        }
        self.blocked = None

    def observe(self, method, params):
        """Called before GoalWorker adopts this original native notification."""
        worker = self.w.goal_worker
        if not worker:
            return
        if method == 'turn/started':
            self.active_turn = None
            self.blocked = None
            self.capture_active(params['turn']['id'], worker.native)
        elif method == 'thread/goal/updated':
            value = self.native(params.get('goal'))
            previous = self.native(worker.native) if worker.native else None
            if (self.active_execution() and self.active_turn and previous
                    and previous['status'] == 'active' and value['status'] == 'blocked'
                    and params.get('turnId') == self.active_turn['turnId'] == self.w.turn_id
                    and goal_binding(previous) == goal_binding(value) == self.active_turn['goalBindingSha256']):
                self.blocked = {'goal': value, 'generation': worker.generation + 1}
            elif value['status'] != 'active':
                self.blocked = None
            elif self.active_execution() and self.w.turn_id and not self.active_turn:
                # A start notification can precede the first active snapshot.
                self.capture_active(self.w.turn_id, value)
        elif method == 'thread/goal/cleared':
            self.blocked = None

    def play(self):
        w = self.w
        if not self.active_execution():
            raise ValueError('The original Goal execution is no longer armed')
        rid = w.goal_worker.activation['requestId']
        command = Goals(w.store).command(w.session_id, rid)
        data = json.loads(command['payload'])
        if command['state'] != 'confirmed' or data.get('action') != 'play':
            raise ValueError('The original human Play is not confirmed')
        client = {key: value for key, value in data.items() if not key.startswith('_')}
        if command['fingerprint'] != digest({'sessionId': w.session_id, **client}):
            raise ValueError('The original Play fingerprint changed')
        captured = data['_goal']
        if captured['threadId'] != w.thread_id:
            raise ValueError('The original Play belongs to another native thread')
        execution = w.config.get('goalExecution')
        if execution:
            if (rid != execution['requestId'] or command['fingerprint'] != execution['commandFingerprint']
                    or digest(captured) != execution['captureSha256']
                    or captured['threadId'] != execution['threadId']
                    or captured['objective'] != execution['objective']):
                raise ValueError('The original frozen Goal execution changed')
        else:
            from goal_live import LiveGoals
            live = LiveGoals(w.store)
            proof = live.evidence(w.session_id, rid)
            if (live.get(w.session_id, rid)['state'] != 'confirmed'
                    or proof['binding']['runId'] != w.run_id
                    or proof['binding']['threadId'] != w.thread_id):
                raise ValueError('The original Live-Play activation changed')
        return {
            'requestId': rid, 'commandFingerprint': command['fingerprint'],
            'captureSha256': digest(captured), 'goalBindingSha256': goal_binding(captured),
            'activationSha256': digest(w.goal_worker.activation), 'controls': self.controls(),
        }

    def original_native(self, scope):
        return inspect_original(Path(self.w.store.directory) / self.w.session_id / 'Codex/native', scope)

    def qualify(self, turn_id, status):
        """Establish a candidate only from a live, original active-to-blocked turn."""
        engine = self.w.config['engine']
        if engine.get('version') != RUNTIME_VERSION or engine.get('sha256') != RUNTIME_SHA256:
            raise ValueError('The original Goal evidence runtime is unqualified')
        worker = self.w.goal_worker
        if not worker or worker.closed or worker.completed_once or self.w.stopping or self.w.done.is_set():
            raise ValueError('The original Goal execution ended or is stopping')
        play = self.play()
        start = self.active_turn
        blocked = self.blocked
        if (not start or not blocked or start['turnId'] != turn_id
                or start['goalBindingSha256'] != play['goalBindingSha256']
                or start['activationSha256'] != play['activationSha256']
                or start['controls'] != play['controls']
                or worker.generation != blocked['generation']
                or self.native(worker.native) != blocked['goal']):
            raise ValueError('The original Goal failure transition is unconfirmed')
        value = blocked['goal']
        if value['tokenBudget'] is not None and value['tokensUsed'] >= value['tokenBudget']:
            raise ValueError('The original Goal budget is exhausted')
        from profile import tools_for
        scope = Scope(self.w.thread_id, turn_id, self.w.config['model'], status,
                      play['goalBindingSha256'], frozenset('studio_' + name for name in tools_for(self.w.config['engine']['profile'])))
        native = self.original_native(scope)
        self.evidence = {'play': play, 'blocked': blocked, 'native': native, 'scope': scope}
        self.started.clear()
        return self.public_evidence()

    def public_evidence(self):
        if self.evidence is None:
            return None
        value = self.evidence
        # Private ledger metadata; no objective, prompt, path or credential.
        return {'play': value['play'], 'blockedGoalSha256': digest(value['blocked']['goal']),
                'blockedGeneration': value['blocked']['generation'], 'native': value['native']}

    def local_gate(self, read_native=False):
        if self.evidence is None:
            raise ValueError('The original Goal retry evidence is missing')
        worker = self.w.goal_worker
        value = self.evidence
        if (not worker or not self.active_execution() or worker.completed_once
                or self.play() != value['play']
                or worker.generation != value['blocked']['generation']
                or self.native(worker.native) != value['blocked']['goal']):
            raise ValueError('The original blocked Goal or controls changed')
        if read_native and self.original_native(value['scope']) != value['native']:
            raise ValueError('The original failed native section changed')

    async def gate(self):
        self.local_gate(read_native=True)
        generation = self.w.goal_worker.generation
        goal = await self.w.client.request('thread/goal/get', {'threadId': self.w.thread_id}, timeout=5)
        if (self.w.goal_worker.generation != generation
                or self.native(goal.get('goal')) != self.evidence['blocked']['goal']):
            raise ValueError('The original native blocked Goal changed during readback')
        self.local_gate(read_native=True)

    def resumed(self, turn_id):
        if self.evidence is None or turn_id == self.retry.failed_turn:
            raise ValueError('The original Goal continuation has no new turn receipt')
        if self.play() != self.evidence['play']:
            raise ValueError('The original Play changed before its continuation')
        self.started.set()
        # Observation only. Failure in accounting never admits or stops work.
        self.w.goal_worker.clock.resume(self.evidence['play']['requestId'])

    def uncertain(self):
        if self.evidence:
            self.w.goal_worker.clock.mark_unknown(self.evidence['play']['requestId'])

    async def submit(self):
        """The shared controller has committed its original claim before this RPC."""
        expected = self.evidence
        self.started.clear()
        result = await self.w.client.request('thread/goal/set', {
            'threadId': self.w.thread_id, 'status': 'active', 'origin': 'automatic'}, timeout=5)
        goal = self.native(result.get('goal'))
        if (goal_binding(goal) != expected['play']['goalBindingSha256']
                or goal['status'] not in ('active', 'complete', 'blocked', 'usageLimited', 'budgetLimited')
                or any(goal[key] < expected['blocked']['goal'][key] for key in ('tokensUsed', 'timeUsedSeconds'))):
            raise ValueError('The original Goal continuation reply contradicts its claim')
        # A successful set reply is not a native model-turn receipt. Never issue
        # a second mutation to compensate for a missing start notification.
        if self.retry.retry_turn is None:
            await asyncio.wait_for(self.started.wait(), 5)
        return self.retry.retry_turn
