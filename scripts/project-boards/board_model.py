"""Bounded public Board projections; never return private paths or SQLite rows."""
import hashlib
import json
from pathlib import Path
from store import ProjectFault

def board(db,ident):
    row=db.execute('SELECT * FROM boards WHERE id=?',(ident,)).fetchone()
    if not row:raise ProjectFault('Board not found in this project.',404)
    return row

def summary(db,row,count=None):
    return {'id':row['id'],'name':row['name'],'description':row['description'],'position':row['position'],
        'revision':row['revision'],'orderRevision':row['order_revision'],'archived':bool(row['archived']),
        'createdAt':row['created_at'],'updatedAt':row['updated_at'],
        'cardCount':db.execute('SELECT COUNT(*) FROM cards WHERE board_id=?',(row['id'],)).fetchone()[0] if count is None else count}

def revision(db):return db.execute('SELECT revision FROM meta WHERE singleton=1').fetchone()[0] if db else 0

def column(db,board_id,ident):
    row=db.execute('SELECT * FROM columns WHERE board_id=? AND id=?',(board_id,ident)).fetchone()
    if not row:raise ProjectFault('Column not found in this Board.',404)
    return row

def card_row(db,board_id,ident):
    row=db.execute('SELECT * FROM cards WHERE board_id=? AND id=?',(board_id,ident)).fetchone()
    if not row:raise ProjectFault('Card not found in this Board.',404)
    return row

def card(db,row,full=False,label_ids=None,counts=None):
    result={'id':row['id'],'boardId':row['board_id'],'columnId':row['column_id'],'title':row['title'],
        'position':row['position'],'revision':row['revision'],'archived':bool(row['archived']),'priority':row['priority'],'dueDate':row['due_date'],
        'createdAt':row['created_at'],'updatedAt':row['updated_at'],
        'labelIds':label_ids if label_ids is not None else [r[0] for r in db.execute('SELECT label_id FROM card_labels WHERE card_id=? ORDER BY label_id',(row['id'],))]}
    if full:
        checks=[{'id':r['id'],'text':r['text'],'checked':bool(r['checked']),'position':r['position'],'revision':r['revision']}
            for r in db.execute('SELECT * FROM checklist WHERE card_id=? ORDER BY position,id',(row['id'],))]
        result.update(description=row['description'],checklist=checks)
    else:
        if counts is None:counts=db.execute('SELECT COALESCE(SUM(checked),0),COUNT(*) FROM checklist WHERE card_id=?',(row['id'],)).fetchone()
        result.update(descriptionPreview=row['description'][:160],checked=counts[0],checklistCount=counts[1])
    return result

def read_version(db):
    if db is None:return {'source':'missing','stamp':'missing'}
    path=next((r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main'),None)
    if not path:return {'source':'memory','stamp':str(revision(db))}
    path=Path(path);info=path.stat();facts=[]
    # SHM read marks can change on a read alone. Committed WAL/rollback-file
    # changes and the original database identity remain part of the stamp.
    for candidate in (path,path.with_name(path.name+'-wal'),path.with_name(path.name+'-journal')):
        try:
            st=candidate.stat(follow_symlinks=False);facts.append([st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns])
        except FileNotFoundError:facts.append(None)
    hashed=lambda value:hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    return {'source':hashed([info.st_dev,info.st_ino]),'stamp':hashed(facts)}

def metadata(db,project_id):
    return {'projectId':project_id,'revision':revision(db),'readVersion':read_version(db),
        'boards':[{'id':r['id'],'revision':r['revision'],'orderRevision':r['order_revision']}
                  for r in db.execute('SELECT id,revision,order_revision FROM boards ORDER BY position,id')] if db else []}

def listing(db,project_id):
    counts={r[0]:r[1] for r in db.execute('SELECT board_id,COUNT(*) FROM cards GROUP BY board_id')} if db else {}
    return {'projectId':project_id,'revision':revision(db),'readVersion':read_version(db),
        'boards':[summary(db,row,counts.get(row['id'],0)) for row in db.execute('SELECT * FROM boards ORDER BY position,id')] if db else []}

def snapshot(db,project_id,ident):
    row=board(db,ident)
    column_counts={r[0]:r[1] for r in db.execute('SELECT column_id,COUNT(*) FROM cards WHERE board_id=? AND archived=0 GROUP BY column_id',(ident,))}
    columns=[{'id':r['id'],'boardId':r['board_id'],'title':r['title'],'position':r['position'],'revision':r['revision'],
        'cardCount':column_counts.get(r['id'],0)} for r in db.execute('SELECT * FROM columns WHERE board_id=? ORDER BY position,id',(ident,))]
    labels_by_card={}
    for value in db.execute('SELECT card_labels.card_id,card_labels.label_id FROM card_labels JOIN cards ON cards.id=card_labels.card_id WHERE cards.board_id=? ORDER BY card_labels.card_id,card_labels.label_id',(ident,)):
        labels_by_card.setdefault(value[0],[]).append(value[1])
    checks={r[0]:(r[1],r[2]) for r in db.execute('SELECT checklist.card_id,SUM(checklist.checked),COUNT(*) FROM checklist JOIN cards ON cards.id=checklist.card_id WHERE cards.board_id=? GROUP BY checklist.card_id',(ident,))}
    cards=[card(db,r,label_ids=labels_by_card.get(r['id'],[]),counts=checks.get(r['id'],(0,0))) for r in db.execute(
        'SELECT cards.id,cards.board_id,cards.column_id,cards.title,substr(cards.description,1,160) AS description,cards.position,cards.revision,cards.archived,cards.priority,cards.due_date,cards.created_at,cards.updated_at '
        'FROM cards JOIN columns ON columns.id=cards.column_id WHERE cards.board_id=? ORDER BY columns.position,cards.position,cards.id',(ident,))]
    labels=[{'id':r['id'],'boardId':r['board_id'],'name':r['name'],'color':r['color'],'revision':r['revision']} for r in db.execute('SELECT * FROM labels WHERE board_id=? ORDER BY name_key,id',(ident,))]
    return {'projectId':project_id,'revision':revision(db),'readVersion':read_version(db),'board':summary(db,row,len(cards)),'columns':columns,'cards':cards,'labels':labels}

def search(db,project_id,ident,query):
    from board_validation import text
    needle=text(query,256,True).casefold();parent=board(db,ident)
    ids=[r['id'] for r in db.execute('SELECT id,title,description FROM cards WHERE board_id=? ORDER BY id',(ident,)) if needle in (r['title']+'\n'+r['description']).casefold()]
    return {'projectId':project_id,'boardId':ident,'boardRevision':parent['revision'],'cardIds':ids}

def receipt(db,rid):
    row=db.execute('SELECT result FROM requests WHERE id=?',(rid,)).fetchone() if db else None
    if not row:raise ProjectFault('No original Board receipt exists for this request.',404)
    return json.loads(row[0])
