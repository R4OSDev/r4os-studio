"""Project-only Roadmap capability; saved preference is separate from tools."""
from profile import ROADMAP_PROFILE
from store import ProjectFault

TOOLS_READY = True


def availability(profile):
    if TOOLS_READY and profile == ROADMAP_PROFILE:
        return {'available': True}
    return {'available': False, 'reason':
            ('New session required for Roadmap tools. This conversation keeps its original native tool profile.'
             if TOOLS_READY else
             'Roadmap tools follow in the next update. New session required after that update; the saved preference already applies to future runs.')}


def require(worker):
    """Use at the host boundary before every Roadmap read or effect."""
    owner = {'type': 'project', 'id': worker.store.project_id}
    if (worker.store.owner_type != 'project' or worker.config.get('owner') != owner
            or worker.config.get('roadmapEnabled') is not True):
        raise ProjectFault('Roadmap access is disabled for this run.', 403)
    if not availability(worker.config.get('engine', {}).get('profile'))['available']:
        raise ProjectFault('This run has no Roadmap tool profile. Its native history was preserved.', 403)
