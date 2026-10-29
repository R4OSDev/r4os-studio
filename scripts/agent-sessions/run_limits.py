"""Host-wide agent concurrency; individual workspace and worker limits still apply."""
DEFAULT_MAX_ACTIVE_RUNS = 16


def max_active_runs(config):
    value = config.get('maxActiveRuns', DEFAULT_MAX_ACTIVE_RUNS)
    if type(value) is not int or value < 1:
        raise ValueError('maxActiveRuns must be a positive integer.')
    return value
