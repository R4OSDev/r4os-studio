"""Current guidance supplements frozen source prompts, without changing declarations."""
from tool_catalog import tool_scope
def compose(config):
    rights = config.get('permissions', {})
    if config.get('owner', {}).get('type') == 'skill': return ''
    if not rights.get('studio.read_development_job'): return git_inspection(config) + project_ssh(config)
    compact = tool_scope(config) == 'project'
    presentation = ('\n\nSTUDIO DEVELOPMENT RESULTS v15: Standard development results are compact and bounded to 12 KiB. '
        'Read view=details or inventory on the same original job and follow nextCursor to reconstruct the complete UTF-8 JSON snapshot; '
        'snapshot hash/revision protects against mixed records. A stale cursor needs a fresh read, never replaying the effect. '
        'Read view=output from its byte offset; continue nextOffset while hasMore, using totalBytes/pageBytes. '
        'truncated/captureLimitReached means the capture limit, not page completeness. captureTruncated=null is unknown for old workers. '
        'Presentation omissions do not delete logs/pins/inventories. Unknown exit status, failed checks and unconfirmed cleanup remain distinct. '
        'Original receipts may be read repeatedly without starting another build/deploy/run/close.') if compact else ''
    return (
        '\n\nSTUDIO LIVE FILE CHECKS: New execution workers periodically read only the original registered outputFiles '
        'inside their deployment. read_development_job shows the most recent observed-stable, missing or unstable '
        'findings and liveFileObservation time; repeated status reads do not require copying files every poll. '
        'Older workers without liveFileObservation do not provide this extra live read path. A file or image receipt '
        'alone is not a completed test. All configured criteria still need verification; an expected exit code '
        'requires the actual application exit. complete_development_job already performs a fresh file/criteria '
        'preflight before authorizing its explicit close, then verifies checks and owned cleanup again afterward. '
        'It never closes on a failed preflight. Only request this effect intentionally for the still-running own '
        'generation with the required run/completion/stop permissions. After a natural process end, inspect the '
        'original final receipts and cleanup; do not repeat completion or relaunch for missing native output/exit evidence. '
        'After a natural Desktop exit removes its window, the current worker can briefly read the acknowledged original '
        'retained completion without a new close or launch. A missing window alone proves neither a crash nor success; '
        'end, real exit code, output coverage and helper cleanup remain separate. Old workers keep their pinned behavior. '
        'desktopLaunchAttempt is a host-only correlation receipt: its hostAttemptId is not a native DESKRUN request. '
        'Only nativeRequestConfirmed=true supplies a native request key. An empty or lost SSH response does not prove '
        'that an app was not started; keep that original effect unknown and do not submit another start. '
        'A terminalRejected own-window result is a final rejection, not a pending action. With the current helper '
        'a matching immutable rejection unlocks a fresh own view; obtain a new focused frame before further input '
        'and never retry a rejected resize automatically. Applied/frame-ready and rejected outcomes stay distinct. '
        'For desktop_content_unconfirmed, a fully bound own visible/focused window can yield a diagnosticOnly, '
        'contentUnconfirmed screenshot. It grants no input frame reference, visual pass or completion readiness. '
        'Process/window proof and DESKRUN content proof remain separate; original STATUS polling is already bounded '
        'by native retention, so do not retry launches or poll forever. '
        'DESKTOP ARGUMENT BUDGET: Deployment receipts/options expose desktopLaunchBudget. The native SSHD '
        'Terminal command limit is 112 UTF-8 bytes after its 15-byte wrapper, including DESKRUN flags, quotes, '
        'path, spaces and optional short WAIT. Use the native 5000ms default. Inspect the bound budget before '
        'choosing arguments; an oversized launch is rejected before admission/controller/quarantine. Never '
        'truncate, split, wrap or retry arguments automatically. Argument-file alternatives require an explicit '
        'app/SDK contract; host Rust builds do not imply a native guest compiler.'
    ) + presentation + original_job_references(config) + editor_shortcuts(config) + key_plans(config) + git_inspection(config) + project_ssh(config)


def original_job_references(config):
    import json
    references = config.get('developmentJobReferences')
    lookup = tool_scope(config) == 'project'
    guidance = ('\n\nSTUDIO ORIGINAL JOB REFERENCES: A lost or truncated tool presentation does not prove rejection. '
        'Never repeat a build/deploy/start to recover its job ID. A developmentReference precedes detailed output; '
        'requestId is the original Studio request UUID, not a native DESKRUN key. '
        'The bounded references below belong only to this session and are a read-only snapshot, not new effects. '
        'Use an entry.id as jobId with studio_read_development_job to obtain its current state. '
        'Missing native admission/end/cleanup remains unknown. ')
    guidance += ('The current tool can also call studio_read_development_job with lookup={} '
        'or lookup={requestId:...} or lookup={originRunId:...,toolCallId:...}; '
        'continue before=nextBefore. Do not combine lookup and jobId. ')
    if references is not None:
        return guidance + json.dumps(references,ensure_ascii=True,separators=(',',':'))
    if config.get('developmentJobReferencesUnavailable'):
        return guidance + 'The original reference index is unavailable; no rejection or missing effect was inferred.'
    return guidance if lookup else ''


def editor_shortcuts(config):
    if tool_scope(config) != 'project': return ''
    return ('\n\nSTUDIO EDITOR SHORTCUTS v1: key="Ctrl+A" with repeat omitted or 1 sends the public '
        'native select-all GUI codepoint to the owned focused client. Requires a fresh own frame and a newly '
        'deployed editor-shortcut-v1 helper. This is one semantic event, not a held physical Ctrl key; '
        'no modifier survives the call. Ctrl+Home/End, arbitrary modifiers and clipboard paste are unavailable. '
        'Read the original accepted/expected receipt and observe a new image or app output before claiming '
        'selection/consumption. Normal key repeat remains 1..16. Never replay uncertain input.')


def key_plans(config):
    if tool_scope(config) != 'project': return ''
    return ('\n\nSTUDIO KEY PLANS v1: kind=keyPlan with a fresh focused own frame can schedule 1..32 '
        'normal key or printable Unicode codepoint steps at monotonic relative atMilliseconds0..2000. Each '
        'step supplies key OR codepoint, not both. A newly deployed key-plan-v1 helper dispatches the plan '
        'without host/model roundtrips between steps. No held keys, physical modifiers, clipboard or Ctrl '
        'shortcuts inside a plan. Stop, original deadline, process/window/focus/geometry or transport loss '
        'abort the rest. Read accepted prefix, actual enqueue-call times, lateness, active and abortedReason '
        'on the original receipt; read_development_job also retains lastKeyPlan. Planned time is not actual '
        'delivery, and enqueue proves neither app consumption nor search/game success. Never change app '
        'time/rules/inventory or replay an uncertain plan. Observe a new own image/output before conclusions.')


def git_inspection(config):
    if tool_scope(config) != 'project': return ''
    return ('\n\nSTUDIO GIT INSPECTION v1: Read Git status/diff/jobs has a separate permission from Push. '
        'Use studio_read_project_git view=status for the bound own repository; page using the original '
        'snapshotId and nextOffset. Inspect view=diff for chosen paths, continuing UTF-8 byte nextOffset; '
        'captureTruncated is explicit and limits are included. Then view=select with snapshotId and an '
        'explicit list of1..512 reviewed changed paths, at most65536 UTF-8 path bytes. Renames require both '
        'old/new paths. View=selection pages the resulting immutable selection. This saves private metadata '
        'only and performs no commit/fetch/pull/push. Total source limits remain10000 files/256MiB/32MiB per '
        'file/1024 bytes per path. studio_push_project REQUIRES selectionId and commitMessage; '
        'there is no files argument or add-all default. It separately needs Push permission and rechecks '
        'the original own run/repository/branch/base/status/hashes before admission and staging. Changed '
        'inputs need a new reviewed selection; never split a milestone arbitrarily or enable rights yourself. '
        'A lost push response is not permission to push again. The pending github.id is the original requestId; '
        'read view=job for that exact ID, even when the original effect is unknown. No automatic reconcile or replay.')


def project_ssh(config):
    if config.get('owner', {}).get('type') != 'project' or not config.get('permissions', {}).get('studio.run_vm_command'): return ''
    return ('\n\nSTUDIO PROJECT VM SSH v1: studio_run_vm_command executes one free R4OS guest command on the currently assigned VM, '
        'without a build or deployment. Studio manages the private SSH connection; the local terminal still has no network. '
        'Separately assigned Remote Hosts use their own tools. The VM must already run with Network and development access enabled; '
        'start it only through the separately permitted VM-start tool or user action. Commands use the native R4OS Terminal, '
        'not a POSIX shell: no invented sh/heredoc/chaining syntax, interactive stdin or PTY. Maximum112 UTF-8 bytes per command; '
        'normal guest permissions and native SSHD restrictions apply. Admission returns the original durable development job immediately; '
        'queued/running is not completion. Read it with studio_read_development_job; view=output optionally selects channel=stdout or stderr, '
        'using that channel\'s nextOffset. Each channel captures at most1MiB and continues draining after truncation. '
        'Only a confirmed commandReturnConfirmed gives the shell exit status; detached descendants are not tracked. '
        'SSH255, loss of transport or stopping the local SSH client may leave guest effects unknown. Inspect the same original job, '
        'use lookup={} to recover a lost reference, and never repeat a command merely to recover its response. '
        'An unresolved guest effect protects the VM until original evidence or an explicit VM end resolves it. '
        'Use studio_stop_development_job to stop the local client; it does not prove the guest process ended. '
        'Do not claim an unsupported file write, successful application or complete output from truncated diagnostics.')
