"""Current guidance supplements frozen source prompts, without changing declarations."""
def compose(config):
    rights = config.get('permissions', {})
    if config.get('owner', {}).get('type') == 'skill' or not rights.get('studio.read_development_job'): return ''
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
        'original final receipts and cleanup; do not repeat completion or relaunch for missing native output/exit evidence.'
    )
