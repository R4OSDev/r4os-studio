"""Optional own-job context, without importing the development worker runtime."""
from functools import cache
import importlib.util
from pathlib import Path
import sqlite3


@cache
def reader():
    path = Path(__file__).resolve().parents[1] / 'project-development/job_reference_reader.py'
    spec = importlib.util.spec_from_file_location('studio_read_only_job_references', path)
    if spec is None or spec.loader is None:
        raise ImportError('The read-only development job adapter is unavailable.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture(projects, project_id, session_id):
    try:
        return {'developmentJobReferences': reader().listing(projects, project_id, session_id, {'limit': 6})}
    except (ImportError, OSError, ValueError, sqlite3.Error):
        # Context enrichment is optional, including its module loading. Missing
        # references never confirm an old effect or authorize a replacement run.
        return {'developmentJobReferencesUnavailable': True}
