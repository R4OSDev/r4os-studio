"""Plan local checkpoints against the full continuation before replacing it."""
import asyncio
from dataclasses import dataclass
from time import monotonic

from active_history import checkpoint_view
from checkpoint_records import choices, select
from context_policy import optimized
from input_budget import admission_tokens
from model_transport import ModelFault
from request_capture import MAX_BODY
from session_store import now
from signed_history import can_restart_messages
from summary_context import human_instruction, payload, request


SOFT_BYTES = 6 * 1024 * 1024
TOTAL_SECONDS = 180


@dataclass(frozen=True)
class Estimate:
    tokens: int
    bytes: int
    images: int

    def public(self):
        return {'estimatedTokens': self.tokens, 'bytes': self.bytes, 'images': self.images}


def estimates(context, size, tokens=None):
    count = context.input_count
    media = count.get('mediaCost', {})
    images=media.get('images') if media.get('version')==3 else sum(
        media.get(key,0) for key in ('qualifiedImages','conservativeImages','historicalImages'))
    return Estimate(count['tokens'] if tokens is None else tokens,size,images)


def continuation(worker, records, through, retained, text, restart=None):
    protected = {item['sequence'] for item in retained}
    exact = [record for record in records if record['sequence'] in protected]
    tail = [record for record in records if record['sequence']>through]
    view = checkpoint_view(text,exact,tail,human_instruction(records),restart)
    return worker.context_results.project(view,records,{'origin':{'retainedContextRecords':retained}})[0]


def largest_input(context, active, candidates, instructions, budget, maximum):
    data, retained, ends = candidates
    report_failures=optimized(context.w.config.get('contextPolicy'),10)
    low, high = 0, len(ends)-1
    best = None
    while low<=high:
        index=(low+high)//2
        candidate=select(data,retained,ends[index])
        messages=request(payload(candidate[1],active,candidate[2],True),report_failures=report_failures)
        tokens,size=context.estimate(messages,instructions,[],summary=budget)
        if size<=MAX_BODY and (maximum is None or tokens<=maximum):
            best=candidate
            low=index+1
        else:
            high=index-1
    return best


class Compaction:
    def __init__(self, context):
        self.context = context
        self.started = None
        self.started_at = None

    def progress(self, state, before, *, after=None, target=None, reason=None):
        if self.started is None:
            self.started = monotonic()
            self.started_at = now()
        self.context.show_compaction({
            'state':state,'runId':self.context.w.run_id,'startedAt':self.started_at,
            'elapsedMs':round((monotonic()-self.started)*1000),
            'completedSteps':int(state=='completed'),'maximumSteps':1,'targetTokens':target,
            'before':before.public(),'after':after.public() if after else None,'reason':reason})

    def interrupted(self, reason):
        previous=getattr(self.context,'compaction_progress',None)
        if self.started is not None and previous and previous['state']=='running':
            self.context.show_compaction({**previous,'state':'stopped','reason':reason,
                'elapsedMs':round((monotonic()-self.started)*1000)})

    async def step(self, instructions, tools, active, records, checkpoint, maximum, target, estimate, size, *, instruction_change=False):
        context = self.context
        worker = context.w
        start_fresh = can_restart_messages(worker.config)
        before = estimates(context,size,estimate if start_fresh else None)
        unsafe = instruction_change or size>MAX_BODY or maximum is not None and estimate>maximum
        reason = 'Studio instructions changed.' if instruction_change else None
        head = worker.history_reader.heads[-1]
        restart = (checkpoint or {}).get('origin', {}).get('messagesContextRestart')
        if start_fresh or restart:
            human = human_instruction(records)
            restart = {'throughSequence':head if start_fresh else restart['throughSequence'],
                       'humanSequence':human['sequence'] if human else None}

        def stop(reason, code='context_retained_limit'):
            self.progress('stopped',before,target=target,reason=reason)
            if unsafe:
                details = {'compactionReason':reason,'inputLimit':maximum} if restart else None
                raise ModelFault(code,not_dispatched=True,details=details)
            return active,False

        candidates = choices(worker,active,checkpoint,MAX_BODY,instruction_change=instruction_change)
        data, retained, ends = candidates
        if not ends:
            return stop('No complete, consumed history group can be summarized.')
        whole=select(data,retained,ends[-1])
        floor=continuation(worker,records,whole[0],whole[2],'',restart)
        floor_tokens,floor_bytes=context.estimate(floor,instructions,tools)
        if floor_bytes>MAX_BODY or maximum is not None and floor_tokens>maximum:
            return stop('Required input and retained tool results exceed the input limit.')

        budget,summary_instructions=context.summary_setup(maximum,instructions)
        planned=largest_input(context,active,candidates,summary_instructions,budget,maximum)
        if planned is None:
            return stop('No complete summary input fits the selected connection.')
        through,_,keep=planned
        candidate=continuation(worker,records,through,keep,'',restart)
        min_tokens,min_bytes=context.estimate(candidate,instructions,tools)
        if target is not None and target-min_tokens<budget['targetTokens']:
            budget,summary_instructions=context.summary_setup(maximum,instructions,target_hint=target-min_tokens)
        token_room=before.tokens-min_tokens
        byte_room=before.bytes-min_bytes
        if not instruction_change and token_room<=288 and byte_room<=8192:
            return stop('The largest admissible summary would leave the active context essentially unchanged.')
        if worker.conversation.head()!=head:
            raise ModelFault('context_history_changed',not_dispatched=True)
        self.progress('running',before,target=target,reason=reason)
        ident,through,text,origin=await context.summarize(
            active,checkpoint,planned,instructions,tools,summary_instructions,budget,announce=False)

        projected=continuation(worker,records,through,keep,text,restart)
        fits,next_bytes=await context.continuation_fit(projected,instructions,tools,maximum)
        if not fits:
            if worker.conversation.head()!=head:
                raise ModelFault('context_history_changed',not_dispatched=True)
            if restart:
                next_tokens = admission_tokens(context.input_count)
                if maximum is not None and next_tokens is not None and next_tokens > maximum:
                    return stop(f'The next request with this summary needs {next_tokens} input tokens.')
            return stop('The next request with this summary does not fit its input limit.')
        after=estimates(context,next_bytes)
        worker.validate_lease()
        if worker.stopping or not worker.active():
            raise asyncio.CancelledError()
        worker.conversation.checkpoint(worker.run_id,ident,through,text,{
            **origin,'sourceHeadSequence':head,'previousCheckpointId':(checkpoint or {}).get('id'),
            'compaction':{'before':before.public(),'after':after.public(),
                          **({'trigger':'instructionsChanged'} if instruction_change else {})},
            **({'messagesContextRestart':restart} if restart else {}),
        },expected_head=head)
        self.progress('completed',before,after=after,target=target,reason=reason)
        return context.report(instructions,tools)[0],True
