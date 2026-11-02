"""Current guidance supplements frozen source prompts, without changing declarations."""
def compose(config):
    rights = config.get('permissions', {})
    if config.get('owner', {}).get('type') == 'skill': return ''
    if not rights.get('studio.read_development_job'): return git_inspection(config)
    compact = config.get('engine',{}).get('profile') in ('studio-tools-v15','studio-tools-v16','studio-tools-v17','studio-tools-v18', 'studio-tools-v19', 'studio-tools-v20', 'studio-tools-v21', 'studio-tools-v22')
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
    ) + presentation + desktop_icons(config) + original_job_references(config) + editor_shortcuts(config) + key_plans(config) + git_inspection(config)


def original_job_references(config):
    import json
    references = config.get('developmentJobReferences')
    lookup = config.get('engine',{}).get('profile') in ('studio-tools-v19','studio-tools-v20', 'studio-tools-v21', 'studio-tools-v22')
    guidance = ('\n\nSTUDIO ORIGINAL JOB REFERENCES: A lost or truncated tool presentation does not prove rejection. '
        'Never repeat a build/deploy/start to recover its job ID. A developmentReference precedes detailed output; '
        'requestId is the original Studio request UUID, not a native DESKRUN key. '
        'The bounded references below belong only to this session and are a read-only snapshot, not new effects. '
        'Use an entry.id as jobId with studio_read_development_job to obtain its current state. '
        'Missing native admission/end/cleanup remains unknown. ')
    if lookup:
        guidance += ('This v19 conversation may also call studio_read_development_job with lookup={} '
            'or lookup={requestId:...} or lookup={originRunId:...,toolCallId:...}; '
            'continue before=nextBefore. Do not combine lookup and jobId. ')
    else:
        guidance += 'This conversation retains its original arguments; use jobId from the references, never invent a lookup argument. '
    if references is not None:
        return guidance + json.dumps(references,ensure_ascii=True,separators=(',',':'))
    if config.get('developmentJobReferencesUnavailable'):
        return guidance + 'The original reference index is unavailable; no rejection or missing effect was inferred.'
    return guidance if lookup else ''


def desktop_icons(config):
    current = config.get('engine', {}).get('profile') in ('studio-tools-v18','studio-tools-v19', 'studio-tools-v20', 'studio-tools-v21', 'studio-tools-v22')
    action = ('For an explicitly requested GUI R4X desktop publication use studio_deploy_project with '
        'desktopShortcut=true and the chosen verified artifactId. Ordinary test deployments omit this option. '
        'It needs Deploy project permission and a current development coordinator; it never starts the app. ') if current else (
        'This conversation retains its original deploy schema: do not invent a desktopShortcut argument. '
        'The browser offers Deploy to desktop on completed GUI builds/deployments; the agent option needs a new v18 session. ')
    return ('\n\nSTUDIO DESKTOP ICONS v1: R4OS already supports application desktop icons. '
        'Notepad declares ICON=Assets/Desktop.ico in module.R4MF; the SDK embeds the first ICON as resource type1/index0. '
        'C:\\R4OS\\DESKTOP\\NOTEPAD.LNK uses R4S_FORMAT=1, SCHEMA=R4LNK, TARGET=<R4X>, TITLE=Notepad, POLICY=gui, ICON=INTERNAL. '
        'Desktop reads the embedded icon directly without running the app. No window-icon setter API is required for this case. '
        'Use a supported bitmap ICO; the reviewed decoder supports uncompressed DIB 8/32-bit, displayed at32x32. '
        'Inspect the actual artifact resourceInventory for icon/index0 and embeddedVerified; a source asset alone is insufficient. '
        + action + 'The publication owns one exact link per project/VM, preserves foreign or edited links, checks old bytes, '
        'and retains the original intent/backup. After uncertainty only original receipt reconciliation is allowed, never another native write. '
        'SSH system-path write protection stays enabled; do not improvise SFTP/shell edits of C:\\R4OS or change VM lifecycle/settings. '
        'A fullReadbackVerified desktopShortcut proves link bytes; iconEmbedded proves the resource inventory only. '
        'consumerVerified/guestVerified remain false until separate real evidence. Visible desktop appearance and launch via that link '
        'are separate from a normal process/window launch. Native own-link activation is currently unavailable: the qualified public '
        'contract has no own-link request with a recoverable native activation/resulting-process receipt. Link resolution followed '
        'by direct R4X launch does not exercise Desktop link activation. Do not resubmit publication or improvise a global click. '
        'Existing own-client screenshot/input tools do not grant global Desktop control. '
        'Do not close acceptance merely from publication, wait for taskbar icons, or treat missing window-icon APIs as a blocker. '
        'Taskbar/window icons are separate features.')


def editor_shortcuts(config):
    if config.get('engine',{}).get('profile') not in ('studio-tools-v20','studio-tools-v21', 'studio-tools-v22'): return ''
    return ('\n\nSTUDIO EDITOR SHORTCUTS v1: key="Ctrl+A" with repeat omitted or 1 sends the public '
        'native select-all GUI codepoint to the owned focused client. Requires a fresh own frame and a newly '
        'deployed editor-shortcut-v1 helper. This is one semantic event, not a held physical Ctrl key; '
        'no modifier survives the call. Ctrl+Home/End, arbitrary modifiers and clipboard paste are unavailable. '
        'Read the original accepted/expected receipt and observe a new image or app output before claiming '
        'selection/consumption. Normal key repeat remains 1..16. Never replay uncertain input.')


def key_plans(config):
    if config.get('engine',{}).get('profile') not in ('studio-tools-v21','studio-tools-v22'): return ''
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
    if config.get('engine',{}).get('profile') != 'studio-tools-v22': return ''
    return ('\n\nSTUDIO GIT INSPECTION v1: Read Git status/diff/jobs has a separate permission from Push. '
        'Use studio_read_project_git view=status for the bound own repository; page using the original '
        'snapshotId and nextOffset. Inspect view=diff for chosen paths, continuing UTF-8 byte nextOffset; '
        'captureTruncated is explicit and limits are included. Then view=select with snapshotId and an '
        'explicit list of1..512 reviewed changed paths, at most65536 UTF-8 path bytes. Renames require both '
        'old/new paths. View=selection pages the resulting immutable selection. This saves private metadata '
        'only and performs no commit/fetch/pull/push. Total source limits remain10000 files/256MiB/32MiB per '
        'file/1024 bytes per path. In this profile studio_push_project REQUIRES selectionId and commitMessage; '
        'there is no files argument or add-all default. It separately needs Push permission and rechecks '
        'the original own run/repository/branch/base/status/hashes before admission and staging. Changed '
        'inputs need a new reviewed selection; never split a milestone arbitrarily or enable rights yourself. '
        'A lost push response is not permission to push again. The pending github.id is the original requestId; '
        'read view=job for that exact ID, even when the original effect is unknown. No automatic reconcile or replay.')
