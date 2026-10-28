"""Private human Kanban data; independent from workspaces, sessions and roadmaps."""
VERSION=1
APPLICATION_ID=0x52344244
SCHEMA='''
CREATE TABLE meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),project_id TEXT NOT NULL UNIQUE,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),feature_level INTEGER NOT NULL DEFAULT 1 CHECK(feature_level>=1));
CREATE TABLE boards(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL DEFAULT '',position INTEGER NOT NULL CHECK(position>=0),
 revision INTEGER NOT NULL DEFAULT 1,order_revision INTEGER NOT NULL DEFAULT 1,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE columns(id TEXT PRIMARY KEY,board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
 title TEXT NOT NULL,position INTEGER NOT NULL CHECK(position>=0),revision INTEGER NOT NULL DEFAULT 1,UNIQUE(board_id,id));
CREATE TABLE cards(id TEXT PRIMARY KEY,board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
 column_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
 position INTEGER NOT NULL CHECK(position>=0),revision INTEGER NOT NULL DEFAULT 1,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high')),due_date TEXT,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(board_id,id),
 FOREIGN KEY(board_id,column_id) REFERENCES columns(board_id,id));
CREATE TABLE checklist(id TEXT PRIMARY KEY,board_id TEXT NOT NULL,card_id TEXT NOT NULL,text TEXT NOT NULL,
 checked INTEGER NOT NULL DEFAULT 0 CHECK(checked IN (0,1)),position INTEGER NOT NULL CHECK(position>=0),
 revision INTEGER NOT NULL DEFAULT 1,FOREIGN KEY(board_id,card_id) REFERENCES cards(board_id,id) ON DELETE CASCADE);
CREATE TABLE labels(id TEXT PRIMARY KEY,board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
 name TEXT NOT NULL,name_key TEXT NOT NULL,color TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,
 UNIQUE(board_id,id),UNIQUE(board_id,name_key));
CREATE TABLE card_labels(board_id TEXT NOT NULL,card_id TEXT NOT NULL,label_id TEXT NOT NULL,
 PRIMARY KEY(card_id,label_id),FOREIGN KEY(board_id,card_id) REFERENCES cards(board_id,id) ON DELETE CASCADE,
 FOREIGN KEY(board_id,label_id) REFERENCES labels(board_id,id) ON DELETE CASCADE);
CREATE TABLE requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX columns_order ON columns(board_id,position,id);
CREATE INDEX cards_order ON cards(board_id,column_id,position,id);
CREATE INDEX checklist_order ON checklist(card_id,position,id);
'''
