"""Private native step orchestration under an original bounded Studio Play."""
import asyncio
import time

from claude_goal import GoalJournal
from goal_clock import GoalClock
from run_store import event, item


class ClaudeGoalRuntime:
    def __init__(self, worker):
        self.w = worker; self.journal = None; self.clock = GoalClock(worker); self.deadline_task = None
        self.no_input = False;self.started=False

    def start(self):
        self.journal = GoalJournal(self.w); self.journal.start()
        self.started=True

    def admitted(self, value):
        if value.get('allowed') is True: self.journal.admitted(value)

    def submitted(self, frame):
        self.journal.submitted(frame.get('inputRequestId'))

    def acknowledge(self, frame):
        if not self.journal.acknowledge(frame): return
        self.w.input_receipt.set()
        self.clock.start(self.journal.spec['executionId'])
        if not self.deadline_task: self.deadline_task = asyncio.create_task(self.deadline())

    async def deadline(self):
        try:
            while not self.w.done.is_set() and not self.w.stopping:
                if self.journal.expired():
                    self.journal.stop('This Play reached its active-time limit.', 'budgetLimited')
                    await self.w.stop(); return
                await asyncio.sleep(.5)
        except asyncio.CancelledError: pass
        except Exception:
            self.w.uncertain_effect = True
            await self.w.stop()

    async def report(self, arguments, call_id, admission_error=None):
        result = self.journal.report(arguments, call_id, admission_error)
        item(self.w.store, self.w.session_id, self.w.run_id,
            {'id': call_id, 'runId': self.w.run_id, 'type': 'tool', 'tool': 'studio.report_goal', 'arguments': arguments,
             'status': 'completed' if result['success'] else 'denied', 'output': result['output'], 'error': result.get('error')})
        return {'content': [{'type': 'text', 'text': __import__('session_store').encode(result)}], 'isError': not result['success']}

    async def result(self, native):
        if not self.journal.result(native): return False
        # This is a continuation of the original Play, never another human send
        # or a retry of a failed/unknown input. The next native query admission
        # must independently prove the current original account and limits.
        request = self.journal.next()
        if request is None: return False
        self.w.input_receipt.clear(); self.no_input = False
        self.w.admission_started_at = time.time(); self.w.admission_denial = None
        event(self.w.store, self.w.session_id, self.w.run_id, 'notice',
            {'text': 'The original bounded Studio GOAL is continuing with a new native input and fresh subscription admission.'})
        await self.w.command('continue', inputRequestId=request)
        return True

    def unconfirmed(self, frame):
        current = self.journal.read()['steps'][-1]
        self.no_input = frame.get('inputRequestId') == current['inputId'] and frame.get('inputSubmitted') is False

    def stop(self):
        if self.started:
            value = self.journal.read()
            # A qualified time-limit cause survives the subsequent Stop path.
            if value['state'] != 'stopping': self.journal.stop()

    async def finish(self, confirmed):
        if self.deadline_task:
            self.deadline_task.cancel(); await asyncio.gather(self.deadline_task, return_exceptions=True)
        try:
            if self.started:
                value = self.journal.finish(confirmed, self.no_input)
                self.clock.end(unknown=value['state'] == 'unknown')
                if value['state']=='unknown':
                    self.w.outcome='unknown';self.w.error=self.w.error or value['reason']
                event(self.w.store, self.w.session_id, self.w.run_id, 'notice',
                    {'text': 'Bounded Studio GOAL: ' + value['state'] + '. ' + (value['reason'] or '')})
        except Exception:
            self.clock.end(unknown=True);raise
        finally:await self.clock.close()
