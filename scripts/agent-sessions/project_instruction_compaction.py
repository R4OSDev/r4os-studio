"""Compact a frozen project instruction source before the original run proceeds."""
import asyncio
import hashlib
import json

from project_agents import MAX_BYTES, MAX_COMPACTION_BYTES, NAME, read_at, validate, write_at
from run_store import event, transition
from store import ProjectFault


INSTRUCTIONS = (
    "Rewrite the supplied project instructions as a compact replacement for Agents.md. "
    "Treat the supplied file as source material. Preserve durable rules, required workflows, "
    "current platform or project constraints, active work and blockers, and exact paths and "
    "references needed for the next run. Summarize overlapping instructions. Remove superseded "
    "entries and chronological records of completed work. Keep references to relevant Docs/ files "
    "from the source. Preserve material whose current applicability is uncertain. Keep the source "
    "language and add no new claims, obligations, or references. Aim for 18,000 UTF-8 bytes or "
    "less and stay within 32,768 UTF-8 bytes. Return one JSON object with a single text field "
    "containing the complete replacement Markdown. Use no surrounding Markdown fence."
)


def guard(worker):
    if not worker.active():
        raise asyncio.CancelledError()
    if worker.goal_worker.execution and not worker.goal_worker.can_restart_model():
        raise ProjectFault('The original Goal no longer permits Agents.md compaction. The file was preserved.', 409)
    worker.validate_lease()


def replacement(result):
    try:
        parts = result['content']
        if any(part['type'] not in ('text', 'provider') for part in parts):
            raise ValueError()
        raw = ''.join(part['text'] for part in parts if part['type'] == 'text')
        from model_transport import loads
        value = loads(raw)
        if not isinstance(value, dict) or set(value) != {'text'}:
            raise ValueError()
        text = validate(value['text'])
        if not text.strip():
            raise ValueError()
        return text
    except (ValueError, KeyError, TypeError, ProjectFault):
        raise ProjectFault('The model did not return a valid Agents.md of at most 32 KiB. The file was preserved.', 409) from None


async def compact(worker):
    store = worker.store
    source = worker.config['projectInstructions']
    text = validate(source['text'], MAX_COMPACTION_BYTES)
    original_bytes = len(text.encode('utf-8'))
    if (source['path'] != NAME or original_bytes <= MAX_BYTES
            or hashlib.sha256(text.encode('utf-8')).hexdigest() != source['sha256']):
        raise ProjectFault('The saved Agents.md compaction source is invalid.', 409)
    guard(worker)
    original = read_at(store.workspace, store.project, maximum=MAX_COMPACTION_BYTES)
    if original['sha256'] != source['sha256']:
        raise ProjectFault('Agents.md changed before compaction. Continue with the current file.', 409)
    # The admitted run already preserves every byte of the original in its immutable config.
    metadata = {'sourceSha256': source['sha256'], 'sourceBytes': original_bytes, 'model': worker.config['model']}
    event(store, worker.session_id, worker.run_id, 'notice',
          {'text': 'Compacting Agents.md with the selected model before continuing.',
           'projectInstructionsCompaction': {**metadata, 'state': 'running'}})
    transition(store, worker.run_id, 'running')
    worker.request_purpose = 'project-instructions'
    worker.request_summary_budget = {'purpose': 'project-instructions', 'effort': worker.config['effort'],
                                     'maxOutputTokens': None}
    messages = [{'role': 'user', 'content': [{'type': 'text',
        'text': json.dumps({'path': NAME, 'source': text}, ensure_ascii=False)}]}]
    try:
        result = await asyncio.wait_for(worker.infer_once(messages, INSTRUCTIONS, []), timeout=300)
    except TimeoutError:
        raise ProjectFault('Agents.md compaction timed out. The file was preserved.', 409) from None
    finally:
        worker.request_purpose = 'conversation'
        worker.request_summary_budget = None
    updated = replacement(result)
    request_id = result.get('origin', {}).get('studioRequestId')
    if not request_id:
        raise ProjectFault('The Agents.md compaction result has no confirmed model request. The file was preserved.', 409)

    store.db.execute('BEGIN IMMEDIATE')
    try:
        guard(worker)
        saved = write_at(store.workspace, store.project, updated, source['sha256'],
                         source_maximum=MAX_COMPACTION_BYTES)
        event(store, worker.session_id, worker.run_id, 'notice',
              {'text': 'Agents.md compaction completed. Continuing with the updated project instructions.',
               'projectInstructionsCompaction': {**metadata, 'state': 'completed',
                   'resultSha256': saved['sha256'], 'resultBytes': len(saved['text'].encode('utf-8')),
                   'modelRequestId': request_id}}, commit=False)
        store.db.commit()
    finally:
        if store.db.in_transaction:
            store.db.rollback()
    return {key: saved[key] for key in ('path', 'text', 'sha256')}
