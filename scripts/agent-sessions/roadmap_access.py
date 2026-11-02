"""Project-only Roadmap capability; saved preference is separate from tools."""
from tool_catalog import tool_scope
from store import ProjectFault

TOOLS_READY = True


def availability(profile):
    return {'available': tool_scope(profile) == 'project'}


def require(worker):
    """Use at the host boundary before every Roadmap read or effect."""
    owner = {'type': 'project', 'id': worker.store.project_id}
    if (worker.store.owner_type != 'project' or worker.config.get('owner') != owner
            or worker.config.get('roadmapEnabled') is not True):
        raise ProjectFault('Roadmap access is disabled for this run.', 403)
