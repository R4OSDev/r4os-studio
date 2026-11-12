"""Preserve the exact Messages prefix before replayed signed reasoning."""
import hashlib

from model_transport import ModelFault, dumps, loads


def protected_route(binding):
    # Unknown Messages connectors may use the same signed-history contract.
    return binding.get('protocol') == 'messages' and binding.get('kind') != 'zai-coding-plan'


def signed(blocks):
    return isinstance(blocks, list) and any(
        block.get('type') == 'redacted_thinking' or block.get('type') == 'thinking' and block.get('signature')
        for block in blocks if isinstance(block, dict))


def latest(messages, binding):
    from portable_history import foreign_selection
    if binding.get('protocol') != 'messages':
        return None
    for record in reversed(messages):
        if record['role'] == 'assistant' and not foreign_selection(record.get('origin', {}).get('selection', {}), binding):
            for part in record['content']:
                if part['type'] == 'provider' and part.get('protocol') == 'messages' and signed(loads(part['value'])):
                    return record
    return None


def bind_catalog(store, sid, config):
    """Continue a signed context with the declarations that produced it."""
    from context_policy import optimized
    binding = {**config.get('apiProvider', {}), 'model':config['model']}
    if not protected_route(binding) or not optimized(config.get('contextPolicy'),1): return
    from conversation import Conversation
    if not Conversation(store,sid).metadata(): return
    rows = store.db.execute("""SELECT * FROM conversation_records WHERE session_id=? AND role='assistant'
        AND kind='message' AND json_type(origin,'$.providerResponseId') IS NOT NULL
        AND json_extract(origin,'$.selection.providerId')=? AND json_extract(origin,'$.selection.model')=?
        ORDER BY seq DESC""", (sid,binding['id'],binding['model']))
    record = None
    for row in rows:
        value = Conversation.present(row)
        if latest([value],binding):
            record = value
            break
    if record is None: return
    from active_tools import ROOT, snapshot, worker_release
    from history_receipts import original_input
    from run_store import get_run
    from store import ProjectFault
    from tool_catalog import declarations, permission_tools, tool_definitions, tool_scope
    from studio_engine import engine
    try:
        prior = loads(get_run(store,record['runId'])['config'])
        if prior['engine'].get('kind')!='studio' or tool_scope(prior)!=tool_scope(config): raise ValueError()
        if prior['engine']==engine(tool_scope(prior),prior['engine'].get('api')):
            root = ROOT
        else:
            root = worker_release(prior,ROOT)
        original = original_input(store,sid,record)
        names = [item['name'].removeprefix('mcp_') for item in original['tools']]
        source = {t['name'] for t in declarations(prior,root)}
        if len(names)!=len(set(names)) or not set(names)<=source: raise ValueError()
        # The archived prefix is not authority to restore an action disabled
        # in the current session. The transport verifies the whole prefix.
        independent = set(permission_tools(config))
        selected=prior.get('toolCatalog',{})
        version = selected.get('version',1)
        definitions=tool_definitions(tool_scope(prior),root)
        operations=set()
        for name in names:
            dispatch=definitions[name[7:]].get('dispatch')
            if dispatch: operations.update(dispatch[action]['tool'] for action in selected.get('actions',{}).get(name,dispatch))
            else: operations.add(name[7:])
        if any(name in independent and not config['permissions'].get('studio.'+name) for name in operations): raise ValueError()
        from profile import NOTE_TOOLS, ROADMAP_TOOLS, UPDATE_TOOLS
        if operations.intersection(ROADMAP_TOOLS) and not config.get('roadmapEnabled'): raise ValueError()
        if operations.intersection(NOTE_TOOLS) and not config.get('environmentNotesEnabled'): raise ValueError()
        if prior.get('updateToolsEnabled') and not config.get('updateToolsEnabled') and operations.intersection(UPDATE_TOOLS):
            raise ValueError()
        mode=selected.get('presentation')
        if mode=='administration' and not config.get('roadmapAdministrationEnabled'): raise ValueError()
        actions={name:items for name,items in selected.get('actions',{}).items() if name in names}
        options = dict(names=names,version=version,presentation=mode,actions=actions,
                       requirements=selected.get('argumentRequirements'))
        catalog = snapshot(prior,root=root,**options)
        if root != ROOT and config['engine'] == engine(tool_scope(config),config['engine'].get('api')):
            # A new admission can use the current runtime when the archived
            # declarations and their broker rules can be reproduced exactly.
            current = tool_definitions(tool_scope(prior),ROOT)
            relevant = operations | {name[7:] for name in names}
            if all(definitions[name] == current.get(name) for name in relevant):
                candidate = snapshot(prior,root=ROOT,**options)
                if candidate['sha256'] == catalog['sha256']:
                    root, catalog = ROOT, candidate
        if root != ROOT:
            policy = config['contextPolicy']
            original_optimization = prior.get('contextPolicy', {}).get('optimization')
            if type(original_optimization) is int:
                policy['optimization'] = min(policy['optimization'], original_optimization)
        config['toolCatalog'] = catalog
        config['engine'] = engine(tool_scope(config),config['engine'].get('api'),root=root)
    except (OSError, ValueError, KeyError, TypeError, ProjectFault, ModelFault):
        raise ProjectFault('The original signed Claude tool catalog is unavailable or the selection changed. Use a fresh context for changed instructions or tools.',409) from None


def prefix(body, count):
    return hashlib.sha256(dumps([body.get('system'), body.get('tools'), body['messages'][:count]]).encode()).hexdigest()


def without_instruction(system, instruction):
    blocks = isinstance(system, list)
    text = system[-1].get('text') if blocks and system and isinstance(system[-1], dict) else system
    if not isinstance(text, str):
        return None
    before, found, after = text.rpartition(instruction)
    if not found:
        return None
    return [*system[:-1], {**system[-1], 'text': before + after}] if blocks else before + after


class Prefix:
    def __init__(self, store, sid, binding, optional_instruction=None):
        self.store = store
        self.sid = sid
        self.binding = binding
        self.record = None
        self.proof = None
        self.optional_instruction = optional_instruction

    def check(self, messages, body):
        record = latest(messages, self.binding)
        if record is None:
            return
        rid = record.get('origin', {}).get('studioRequestId')
        if self.record != rid or self.proof is None:
            from history_receipts import original_input
            original = original_input(self.store, self.sid, record)
            self.record = rid
            self.proof = (len(original['messages']), prefix(original, len(original['messages']))) if (
                isinstance(original, dict) and isinstance(original.get('messages'), list)) else None
        wire = body['messages']
        position = next((i for i in range(len(wire) - 1, -1, -1)
                         if wire[i]['role'] == 'assistant' and signed(wire[i]['content'])), None)
        if self.proof is None or position != self.proof[0]:
            raise ModelFault('context_signed_prefix', not_dispatched=True)
        if prefix(body, position) == self.proof[1]:
            return
        if self.optional_instruction:
            system = body.get('system')
            previous = without_instruction(system, self.optional_instruction)
            if previous is not None:
                body['system'] = previous
                # Older signed blocks predate this generated system section.
                # Accept its removal only if the entire original prefix matches.
                if prefix(body, position) == self.proof[1]:
                    return
                body['system'] = system
        raise ModelFault('context_signed_prefix', not_dispatched=True)
