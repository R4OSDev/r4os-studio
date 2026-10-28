"""Explicit atomic storage publication and shared project lifetime only."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import sys
import uuid

sys.path.append(str(Path(__file__).resolve().parents[1]/'projects'))
from project_maintenance import project
from project_use import acquire
from layout import project_directory,sync,workspace
from store import ProjectFault
from board_schema import SCHEMA,VERSION,APPLICATION_ID

MAX_DATABASE_BYTES=128*1024*1024
SUPPORTED_FEATURE_LEVEL=1

def regular(path):
    info=path.lstat()
    if (path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
            or info.st_uid!=os.getuid() or info.st_size>MAX_DATABASE_BYTES):
        raise ProjectFault('Invalid Board storage. Existing data was preserved.',503)

def folder(path):
    if path.resolve(strict=True)!=path or not path.is_dir():raise ProjectFault('Invalid Board directory. Existing data was preserved.',503)

def initialize(path,project_id):
    lock=path.parent/'.initialize.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        regular(lock);fcntl.flock(fd,fcntl.LOCK_EX)
        if path.exists() or path.is_symlink():return
        if list(path.parent.glob('.initializing-*.sqlite')):raise ProjectFault('Interrupted Board initialization needs maintenance. Existing files were preserved.',503)
        stage=path.parent/('.initializing-'+str(uuid.uuid4())+'.sqlite')
        created=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(created)
        db=sqlite3.connect(stage)
        try:
            db.execute('PRAGMA synchronous=FULL');db.executescript('BEGIN IMMEDIATE;'+SCHEMA)
            db.execute('INSERT INTO meta VALUES(1,?,0,1)',(project_id,))
            db.execute('PRAGMA application_id='+str(APPLICATION_ID));db.execute('PRAGMA user_version='+str(VERSION));db.commit()
        finally:db.close()
        regular(stage)
        with stage.open('rb') as source:os.fsync(source.fileno())
        # link is create-only. No existing database can be replaced.
        os.link(stage,path,follow_symlinks=False);stage.unlink();sync(path.parent)
    finally:os.close(fd)

@contextmanager
def connection(projects,project_id,create=False):
    projects=Path(projects).absolute()
    with acquire(projects,project_id):
        try:project(projects,project_id)
        except FileNotFoundError:raise ProjectFault('Project not found.',404) from None
        if not (projects/project_id/'Workspace').exists():raise ProjectFault('Migrate this project to the private Workspace layout before using Boards.',409)
        workspace(projects,project_id,require_current=True)
        parent=project_directory(projects,project_id)/'Boards'
        if not parent.exists() and not parent.is_symlink():
            if not create:yield None;return
            parent.mkdir(mode=0o700,exist_ok=True);sync(parent.parent)
        folder(parent);path=parent/'Boards.sqlite'
        for suffix in ('-journal','-wal','-shm'):
            other=path.with_name(path.name+suffix)
            if other.exists() or other.is_symlink():
                regular(other)
                if not path.exists():raise ProjectFault('Interrupted Board storage needs maintenance.',503)
        if not path.exists() and not path.is_symlink():
            if not create:yield None;return
            initialize(path,project_id)
        regular(path);db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=3)
        try:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
            if (db.execute('PRAGMA user_version').fetchone()[0]!=VERSION or db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID
                    or db.execute('PRAGMA quick_check(1)').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone()):
                raise ProjectFault('Unsupported or damaged Board data. Existing database was preserved.',503)
            binding=db.execute('SELECT project_id,feature_level FROM meta WHERE singleton=1').fetchone()
            if not binding or binding[0]!=project_id:raise ProjectFault('Board storage belongs to another project.',503)
            if not 1<=binding[1]<=SUPPORTED_FEATURE_LEVEL:raise ProjectFault('This Board data needs a newer Studio release. Existing data was preserved.',503)
            if binding[1]==1 and any(db.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone() for table in ('cards','labels','checklist','card_labels')):
                raise ProjectFault('Board feature metadata needs maintenance. Existing data was preserved.',503)
            page_size=db.execute('PRAGMA page_size').fetchone()[0];db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//page_size))
            yield db
        finally:db.close()
