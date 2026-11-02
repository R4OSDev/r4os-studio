"""Development API adapter for the shared read-only original job index."""
from contracts import DevelopmentFault
import job_reference_reader as reader

KINDS = reader.KINDS


def validate(query):
    try:
        return reader.validate(query)
    except reader.JobReferenceFault as error:
        raise DevelopmentFault(str(error), error.code) from None


def listing(projects, project_id, session_id, query=None):
    try:
        return reader.listing(projects, project_id, session_id, query)
    except reader.JobReferenceFault as error:
        raise DevelopmentFault(str(error), error.code) from None
