"""Read complete original failed-turn evidence; never grant execution itself.

Pinned native0.163.0 persists function calls before executing them. A complete
contiguous failed-turn section can exclude model Goal mutation. The controller
must additionally establish the original live Play, native active-to-blocked
transition, current account/lease, controls, effects and bounded retry claim.
No historical prefix or caller-selected end offset is accepted here.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from provider_errors import response_body_decode_failure

RUNTIME_VERSION='0.163.0'
RUNTIME_SHA256='399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215'
MAX_LINE=524288
MAX_TAIL=8*1024*1024
MAX_RECORDS=16384
SAFE_EVENTS=frozenset({'token_count','thread_settings_applied','agent_message',
    'agent_reasoning','agent_reasoning_raw_content','mcp_tool_call_end',
    'web_search_end','image_generation_end','item_completed','user_message'})
SAFE_METADATA=frozenset({'world_state','token_usage_record','security_risk_score','retained_context'})

class UnqualifiedEvidence(ValueError):pass

@dataclass(frozen=True)
class Scope:
    thread_id:str
    failed_turn_id:str
    native_model:str
    http_status:int|None
    goal_binding_sha256:str
    studio_functions:frozenset[str]
    failure_code:str='httpConnectionFailed'

    def validate(self):
        for value in (self.thread_id,self.failed_turn_id):
            if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',value):
                raise UnqualifiedEvidence('The original native identity is invalid.')
        qualified_failure=(self.failure_code=='httpConnectionFailed' and type(self.http_status) is int
                           and self.http_status in (502,503,504)
                           or self.failure_code=='responseBodyDecodeFailed' and self.http_status is None)
        if (not self.native_model or len(self.native_model.encode())>256 or not qualified_failure
            or not re.fullmatch('[a-f0-9]{64}',self.goal_binding_sha256)
            or not isinstance(self.studio_functions,frozenset)
            or len(self.studio_functions)>128
            or any(not re.fullmatch('studio_[a-z][a-z0-9_]{0,79}',s) for s in self.studio_functions)):
            raise UnqualifiedEvidence('The original frozen evidence scope is invalid.')

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def goal_binding(goal):
    return digest({key:goal.get(key) for key in ('threadId','objective','tokenBudget','createdAt')})

def object_pairs(values):
    result={}
    for key,value in values:
        if key in result:raise UnqualifiedEvidence('Duplicate native evidence fields.')
        result[key]=value
    return result

def invalid_constant(_):raise UnqualifiedEvidence('Invalid native JSON number.')

def decode(line):
    if len(line)>MAX_LINE or not line.endswith(b'\n'):
        raise UnqualifiedEvidence('The original native record is oversized or incomplete.')
    try:value=json.loads(line,object_pairs_hook=object_pairs,parse_constant=invalid_constant)
    except (ValueError,UnicodeError,RecursionError) as error:
        raise UnqualifiedEvidence('The original native record cannot be decoded.') from error
    if not isinstance(value,dict) or not isinstance(value.get('payload'),dict):
        raise UnqualifiedEvidence('The original native record shape is unsupported.')
    return value

def signature(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]

def opaque(value):
    return (isinstance(value,str) and 0<len(value.encode())<=256
        and not any(ord(c)<=32 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in value))

def text_only_compaction(payload,scope):
    """A pinned completed checkpoint is data, not a replacement execution log.

    Keep scanning the entire original turn across it. Accept only the observed
    remote checkpoint with messages/encrypted compaction and no embedded tools;
    never use its summary as proof of a tool result or Goal control.
    """
    fields={'message','replacement_history','replacement_history_metadata','guardian_history',
        'retained_context','mcp_resource_origins','window_number','first_window_id','previous_window_id',
        'window_id','compaction_response_id','latest_token_usage_record','resume_metadata'}
    history=payload.get('replacement_history');resume=payload.get('resume_metadata')
    if (scope.failure_code!='responseBodyDecodeFailed' or set(payload)-fields
        or payload.get('message')!='' or not isinstance(history,list) or not 0<len(history)<=1024
        or not isinstance(resume,dict) or resume.get('last_started_turn_id')!=scope.failed_turn_id):
        return False
    metadata=payload.get('replacement_history_metadata')
    if metadata is not None and (not isinstance(metadata,list) or len(metadata)!=len(history)
                                or any(not isinstance(item,dict) for item in metadata)):
        return False
    for item in history:
        if not isinstance(item,dict):return False
        if item.get('type')=='compaction':
            if not isinstance(item.get('encrypted_content'),str) or not item['encrypted_content']:return False
        elif item.get('type')=='message':
            if item.get('role') not in ('user','developer','assistant') or not isinstance(item.get('content'),list):return False
            if any(not isinstance(content,dict) or content.get('type') not in
                   ('input_text','output_text','input_image','refusal') for content in item['content']):return False
        else:return False
    return any(item['type']=='compaction' for item in history)

def inspect_stream(handle,relative_path,scope):
    before=os.fstat(handle.fileno())
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
        or before.st_nlink!=1 or before.st_mode & 0o022):
        raise UnqualifiedEvidence('The original native file ownership or type changed.')
    end=before.st_size
    header=handle.readline(MAX_LINE+1);meta=decode(header)
    if (meta.get('type')!='session_meta' or meta['payload'].get('id')!=scope.thread_id
        or meta['payload'].get('cli_version')!=RUNTIME_VERSION or meta['payload'].get('cwd')!='/workspace'):
        raise UnqualifiedEvidence('The original native session header does not match.')
    offset=max(len(header),end-MAX_TAIL);handle.seek(offset)
    if offset>len(header):
        discarded=handle.readline(MAX_LINE+1)
        while discarded and not discarded.endswith(b'\n') and handle.tell()<end:
            discarded=handle.readline(min(MAX_LINE+1,end-handle.tell()))
        if not discarded.endswith(b'\n'):
            raise UnqualifiedEvidence('The bounded native suffix starts inside an incomplete record.')
    start=None;terminal=None;previous_ordinal=None;contexts=0;count=0
    issued=set();returned=set();saw_blocked=False;section=hashlib.sha256();compactions=0
    while handle.tell()<end:
        at=handle.tell();line=handle.readline(min(MAX_LINE+1,end-handle.tell()))
        if start is None:
            if len(line)>MAX_LINE or not line.endswith(b'\n'):
                while line and not line.endswith(b'\n') and handle.tell()<end:
                    line=handle.readline(min(MAX_LINE+1,end-handle.tell()))
                continue
            try:value=decode(line)
            except UnqualifiedEvidence:continue
        else:value=decode(line)
        count+=1
        if count>MAX_RECORDS:raise UnqualifiedEvidence('The native suffix exceeds its record bound.')
        kind=value.get('type');payload=value['payload'];event=payload.get('type')
        matching_start=(kind=='event_msg' and event=='task_started' and payload.get('turn_id')==scope.failed_turn_id)
        if matching_start:
            if start is not None:raise UnqualifiedEvidence('The original native turn start is duplicated.')
            start=at
        if kind=='turn_context' and payload.get('turn_id')==scope.failed_turn_id:
            if payload.get('model')!=scope.native_model or payload.get('cwd')!='/workspace':
                raise UnqualifiedEvidence('The original native model or workspace changed.')
            contexts+=1
        if start is None:continue
        ordinal=value.get('ordinal')
        if type(ordinal) is not int or ordinal<0 or previous_ordinal is not None and ordinal!=previous_ordinal+1:
            raise UnqualifiedEvidence('The original native section has missing or reordered records.')
        previous_ordinal=ordinal;section.update(line)
        if matching_start:continue
        if terminal is not None and not (kind=='token_usage_record' or kind=='event_msg' and event in ('token_count','thread_goal_updated')):
            raise UnqualifiedEvidence('New native activity follows the failed terminal record.')
        if kind=='event_msg':
            if event=='task_complete':
                error=payload.get('error')
                if not isinstance(error,dict):raise UnqualifiedEvidence('The final native failure is missing.')
                info=error.get('codex_error_info')
                exact_failure=(info=={'http_connection_failed':{'http_status_code':scope.http_status}}
                    if scope.failure_code=='httpConnectionFailed'
                    else response_body_decode_failure(info,error.get('message')))
                if (terminal is not None or payload.get('turn_id')!=scope.failed_turn_id
                    or not exact_failure):
                    raise UnqualifiedEvidence('The exact final native failure is missing.')
                terminal=at
            elif event=='thread_goal_updated':
                goal=payload.get('goal')
                if not isinstance(goal,dict) or goal_binding(goal)!=scope.goal_binding_sha256:
                    raise UnqualifiedEvidence('The original native Goal binding changed.')
                status=goal.get('status')
                if (status not in ('active','blocked') or saw_blocked and status!='blocked'
                    or terminal is not None and status!='blocked'):
                    raise UnqualifiedEvidence('A native Goal control supersedes this failure.')
                saw_blocked=saw_blocked or status=='blocked'
            elif event not in SAFE_EVENTS:
                raise UnqualifiedEvidence('An unsupported native control or event occurs in the failed turn.')
        elif kind=='response_item':
            response_type=payload.get('type')
            metadata=payload.get('internal_chat_message_metadata_passthrough')
            if metadata is not None and (not isinstance(metadata,dict) or metadata.get('turn_id') not in (None,scope.failed_turn_id)):
                raise UnqualifiedEvidence('A model record names another native turn.')
            if response_type=='function_call':
                name=payload.get('name');namespace=payload.get('namespace')
                if isinstance(name,str) and name.startswith('functions.') and namespace is None:name=name[len('functions.'):]
                if namespace not in (None,'functions') or name not in scope.studio_functions|{'get_goal'}:
                    raise UnqualifiedEvidence('Native Goal mutation or an unqualified function call was recorded.')
                call=payload.get('call_id')
                if not opaque(call) or call in issued or len(issued)>=1024:
                    raise UnqualifiedEvidence('The native function call identity is unconfirmed.')
                issued.add(call)
            elif response_type=='function_call_output':
                call=payload.get('call_id')
                if not opaque(call) or call not in issued or call in returned:
                    raise UnqualifiedEvidence('The native function result is missing or foreign.')
                returned.add(call)
            elif response_type in ('web_search_call','image_generation_call'):
                if payload.get('status')!='completed':raise UnqualifiedEvidence('The native hosted tool is unconfirmed.')
            elif response_type not in ('message','agent_message','reasoning'):
                raise UnqualifiedEvidence('An unsupported model record occurs in this native turn.')
        elif kind=='turn_context':
            if payload.get('turn_id')!=scope.failed_turn_id:
                raise UnqualifiedEvidence('The original native turn context changed.')
        elif kind=='compacted':
            if issued!=returned or not text_only_compaction(payload,scope):
                raise UnqualifiedEvidence('The native compaction checkpoint is unqualified or has outstanding tools.')
            compactions+=1
        elif kind not in SAFE_METADATA:
            raise UnqualifiedEvidence('A compaction, replacement or unknown native record prevents continuation.')
    after=os.fstat(handle.fileno())
    if signature(before)!=signature(after) or handle.tell()!=end:
        raise UnqualifiedEvidence('The original native evidence changed during the read.')
    if start is None or terminal is None or not contexts or issued!=returned:
        raise UnqualifiedEvidence('The original native turn coverage or function results are incomplete.')
    proof={'currentNativeEnd':end==before.st_size,'runtimeSha256':RUNTIME_SHA256,'threadId':scope.thread_id,'failedTurnId':scope.failed_turn_id,
        'fileSha256':digest(relative_path),'fileSnapshot':signature(after),'headerSha256':hashlib.sha256(header).hexdigest(),
        'turnStartOffset':start,'terminalOffset':terminal,'lastOrdinal':previous_ordinal,
        'sectionSha256':section.hexdigest(),'goalBindingSha256':scope.goal_binding_sha256,
        'functionCallsChecked':len(issued),'modelGoalMutationExcluded':True}
    if scope.failure_code=='responseBodyDecodeFailed':proof['compactionsChecked']=compactions
    return proof

def inspect_original(native_root,scope):
    """Inspect exactly one original file under the trusted worker-owned root.

    This is evidence only. A second read must match the entire returned proof
    before any future execution claim. No missing scan result grants authority.
    """
    scope.validate();root=Path(native_root)
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    result=None;directories=0;files=0
    try:
        info=os.fstat(rootfd)
        if info.st_uid!=os.getuid() or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise UnqualifiedEvidence('The original native directory owner changed.')
        for parent,dirs,names,parentfd in os.fwalk('.',topdown=True,follow_symlinks=False,dir_fd=rootfd):
            directories+=1;files+=len(names)
            if directories>128 or files>4096 or len(Path(parent).parts)>8:
                raise UnqualifiedEvidence('The original native file lookup exceeds its bounds.')
            dirs[:]=[name for name in dirs if not stat.S_ISLNK(os.stat(name,dir_fd=parentfd,follow_symlinks=False).st_mode)]
            for name in names:
                if not name.endswith('-'+scope.thread_id+'.jsonl'):continue
                if result is not None:raise UnqualifiedEvidence('More than one original native file matches.')
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parentfd)
                with os.fdopen(fd,'rb') as handle:
                    result=inspect_stream(handle,str(Path(parent)/name),scope)
        if result is None:raise UnqualifiedEvidence('The exact original native file is unavailable.')
        return result
    finally:os.close(rootfd)
