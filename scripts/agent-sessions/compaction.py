"""Plan local checkpoints against the full continuation before replacing it."""
import asyncio
from dataclasses import dataclass
from time import monotonic

from active_history import checkpoint_view
from checkpoint_records import choices, select
from model_transport import ModelFault
from request_capture import MAX_BODY
from session_store import now
from summary_context import human_instruction, payload, request


SOFT_BYTES = 6 * 1024 * 1024
MAX_STEPS = 3
TOTAL_SECONDS = 180


@dataclass(frozen=True)
class Estimate:
    tokens: int
    bytes: int
    images: int

    def public(self):
        return {'estimatedTokens': self.tokens, 'bytes': self.bytes, 'images': self.images}


def estimates(context, size):
    count = context.input_count
    media = count.get('mediaCost', {})
    return Estimate(count['tokens'],size,media.get('qualifiedImages',0)+media.get('conservativeImages',0))


def continuation(worker, records, through, retained, text):
    protected = {item['sequence'] for item in retained}
    exact = [record for record in records if record['sequence'] in protected]
    tail = [record for record in records if record['sequence']>through]
    view = checkpoint_view(text,exact,tail,human_instruction(records))
    return worker.context_results.project(view,records,{'origin':{'retainedContextRecords':retained}})[0]


def largest_input(context, active, candidates, instructions, budget, maximum):
    data, retained, ends = candidates
    low, high = 0, len(ends)-1
    best = None
    while low<=high:
        index=(low+high)//2
        candidate=select(data,retained,ends[index])
        messages=request(payload(candidate[1],active,candidate[2],True))
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
        self.steps = 0
        self.started = None
        self.started_at = None

    def progress(self, state, before, *, after=None, target=None, reason=None):
        if self.started is None:
            self.started = monotonic()
            self.started_at = now()
        self.context.show_compaction({
            'state':state,'runId':self.context.w.run_id,'startedAt':self.started_at,
            'elapsedMs':round((monotonic()-self.started)*1000),
            'completedSteps':self.steps,'maximumSteps':MAX_STEPS,'targetTokens':target,
            'before':before.public(),'after':after.public() if after else None,'reason':reason})

    def interrupted(self, reason):
        previous=getattr(self.context,'compaction_progress',None)
        if self.started is not None and previous and previous['state']=='running':
            self.context.show_compaction({**previous,'state':'stopped','reason':reason,
                'elapsedMs':round((monotonic()-self.started)*1000)})

    async def step(self, instructions, tools, active, records, checkpoint, maximum, target, estimate, size):
        context = self.context
        worker = context.w
        before = estimates(context,size)
        unsafe = size>MAX_BODY or maximum is not None and estimate>maximum
        head = worker.history_reader.heads[-1]

        def stop(reason, code='context_retained_limit'):
            self.progress('stopped',before,target=target,reason=reason)
            if unsafe:
                raise ModelFault(code,not_dispatched=True)
            return active,False

        if self.steps>=MAX_STEPS:
            return stop('The maximum number of compaction steps was reached.','context_compaction_bound')

        candidates = choices(worker,active,checkpoint,MAX_BODY)
        data, retained, ends = candidates
        if not ends:
            return stop('No complete, consumed history group can be summarized.')
        whole=select(data,retained,ends[-1])
        floor=continuation(worker,records,whole[0],whole[2],'')
        floor_tokens,floor_bytes=context.estimate(floor,instructions,tools)
        if floor_bytes>MAX_BODY or maximum is not None and floor_tokens>maximum:
            return stop('Required input and exact unresolved observations exceed the input limit.')

        budget,summary_instructions=context.summary_setup(maximum,instructions)
        planned=largest_input(context,active,candidates,summary_instructions,budget,maximum)
        if planned is None:
            return stop('No complete summary input fits the selected connection.')
        through,_,keep=planned
        candidate=continuation(worker,records,through,keep,'')
        min_tokens,min_bytes=context.estimate(candidate,instructions,tools)
        if target is not None and target-min_tokens<budget['targetTokens']:
            budget,summary_instructions=context.summary_setup(maximum,instructions,target_hint=target-min_tokens)
        token_room=before.tokens-min_tokens
        byte_room=before.bytes-min_bytes
        if token_room<=288 and byte_room<=8192:
            return stop('The largest admissible summary would leave the active context essentially unchanged.')
        if worker.conversation.head()!=head:
            raise ModelFault('context_history_changed',not_dispatched=True)
        self.progress('running',before,target=target)
        ident,through,text,origin=await context.summarize(
            active,checkpoint,planned,instructions,tools,summary_instructions,budget,announce=False)

        projected=continuation(worker,records,through,keep,text)
        _,next_bytes=context.estimate(projected,instructions,tools)
        after=estimates(context,next_bytes)
        small_gain=after.tokens>=before.tokens-32 and after.bytes>=before.bytes-4096
        new_token_overflow=maximum is not None and before.tokens<=maximum<after.tokens
        new_byte_overflow=before.bytes<=MAX_BODY<after.bytes
        if small_gain or new_token_overflow or new_byte_overflow:
            self.progress('stopped',before,target=target,reason='The confirmed summary would not make the next request smaller within its limits.')
            raise ModelFault('context_summary_no_progress')
        worker.validate_lease()
        if worker.stopping or not worker.active():
            raise asyncio.CancelledError()
        worker.conversation.checkpoint(worker.run_id,ident,through,text,{
            **origin,'sourceHeadSequence':head,'previousCheckpointId':(checkpoint or {}).get('id'),
            'compaction':{'before':before.public(),'after':after.public()},
        },expected_head=head)
        self.steps += 1
        self.progress('completed',before,after=after,target=target)
        return context.report(instructions,tools)[0],True
