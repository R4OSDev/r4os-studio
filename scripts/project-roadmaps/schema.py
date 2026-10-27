"""Project-private roadmap schema. No workspace or session data lives here."""

SCHEMA_VERSION = 1
APPLICATION_ID = 0x5234524D  # R4RM
SCHEMA = '''
CREATE TABLE roadmap (
    id TEXT PRIMARY KEY,
    singleton INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK(singleton=1),
    project_id TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    current_version_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY(id,current_version_id) REFERENCES versions(roadmap_id,id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE versions (
    id TEXT PRIMARY KEY, roadmap_id TEXT NOT NULL REFERENCES roadmap(id),
    major INTEGER NOT NULL CHECK(major BETWEEN 0 AND 2147483647),
    minor INTEGER NOT NULL CHECK(minor BETWEEN 0 AND 2147483647),
    title TEXT NOT NULL, vision TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','complete','discarded')),
    position INTEGER NOT NULL CHECK(position>=0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(roadmap_id,major,minor), UNIQUE(roadmap_id,id)
);
CREATE TABLE subversions (
    id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    patch INTEGER NOT NULL CHECK(patch BETWEEN 0 AND 2147483647),
    title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','complete','discarded')),
    position INTEGER NOT NULL CHECK(position>=0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(version_id,patch)
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, subversion_id TEXT NOT NULL REFERENCES subversions(id) ON DELETE CASCADE,
    description TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','discarded')),
    position INTEGER NOT NULL CHECK(position>=0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE acceptances (
    id TEXT PRIMARY KEY, subversion_id TEXT NOT NULL REFERENCES subversions(id) ON DELETE CASCADE,
    description TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','discarded')),
    position INTEGER NOT NULL CHECK(position>=0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX subversions_order ON subversions(version_id,position,id);
CREATE INDEX tasks_order ON tasks(subversion_id,position,id);
CREATE INDEX acceptances_order ON acceptances(subversion_id,position,id);
CREATE TABLE receipts (
    request_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
    revision INTEGER NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE workflows (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES versions(id),
    phase TEXT NOT NULL, payload TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
'''
