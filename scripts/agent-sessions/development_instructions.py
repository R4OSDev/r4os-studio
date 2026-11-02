"""Current guidance supplements frozen source prompts, without changing declarations."""
def compose(config):
    rights = config.get('permissions', {})
    if config.get('owner', {}).get('type') == 'skill' or not rights.get('studio.read_development_job'): return ''
    compact = config.get('engine',{}).get('profile') in ('studio-tools-v15','studio-tools-v16','studio-tools-v17','studio-tools-v18')
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
    ) + presentation + desktop_icons(config)


def desktop_icons(config):
    current = config.get('engine', {}).get('profile') == 'studio-tools-v18'
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
        'are separate from a normal process/window launch. Existing own-client screenshot/input tools do not grant global Desktop control. '
        'Do not close acceptance merely from publication, wait for taskbar icons, or treat missing window-icon APIs as a blocker. '
        'Taskbar/window icons are separate features.')
