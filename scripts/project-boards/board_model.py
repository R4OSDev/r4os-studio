"""Bounded public Board projections; never return private paths or SQLite rows."""
import json
from store import ProjectFault

def board(db,ident):
    row=db.execute('SELECT * FROM boards WHERE id=?',(ident,)).fetchone()
    if not row:raise ProjectFault('Board not found in this project.',404)
    return row

def summary(db,row):
    return {'id':row['id'],'name':row['name'],'description':row['description'],'position':row['position'],
        'revision':row['revision'],'orderRevision':row['order_revision'],'archived':bool(row['archived']),
        'createdAt':row['created_at'],'updatedAt':row['updated_at'],
        'cardCount':db.execute('SELECT COUNT(*) FROM cards WHERE board_id=?',(row['id'],)).fetchone()[0]}

def revision(db):return db.execute('SELECT revision FROM meta WHERE singleton=1').fetchone()[0] if db else 0

def column(db,board_id,ident):
    row=db.execute('SELECT * FROM columns WHERE board_id=? AND id=?',(board_id,ident)).fetchone()
    if not row:raise ProjectFault('Column not found in this Board.',404)
    return row

def card_row(db,board_id,ident):
    row=db.execute('SELECT * FROM cards WHERE board_id=? AND id=?',(board_id,ident)).fetchone()
    if not row:raise ProjectFault('Card not found in this Board.',404)
    return row

def card(db,row,full=False):
    result={'id':row['id'],'boardId':row['board_id'],'columnId':row['column_id'],'title':row['title'],
        'position':row['position'],'revision':row['revision'],'archived':bool(row['archived']),'priority':row['priority'],'dueDate':row['due_date'],
        'createdAt':row['created_at'],'updatedAt':row['updated_at'],
        'labelIds':[r[0] for r in db.execute('SELECT label_id FROM card_labels WHERE card_id=? ORDER BY label_id',(row['id'],))]}
    checks=[{'id':r['id'],'text':r['text'],'checked':bool(r['checked']),'position':r['position'],'revision':r['revision']}
        for r in db.execute('SELECT * FROM checklist WHERE card_id=? ORDER BY position,id',(row['id'],))]
    if full:result.update(description=row['description'],checklist=checks)
    else:result.update(descriptionPreview=row['description'][:160],checked=sum(c['checked'] for c in checks),checklistCount=len(checks))
    return result

def listing(db,project_id):
    return {'projectId':project_id,'revision':revision(db),'boards':[summary(db,row) for row in db.execute('SELECT * FROM boards ORDER BY position,id')] if db else []}

def snapshot(db,project_id,ident):
    row=board(db,ident)
    columns=[{'id':r['id'],'boardId':r['board_id'],'title':r['title'],'position':r['position'],'revision':r['revision'],
        'cardCount':db.execute('SELECT COUNT(*) FROM cards WHERE column_id=? AND archived=0',(r['id'],)).fetchone()[0]}
        for r in db.execute('SELECT * FROM columns WHERE board_id=? ORDER BY position,id',(ident,))]
    cards=[card(db,r) for r in db.execute('SELECT cards.* FROM cards JOIN columns ON columns.id=cards.column_id WHERE cards.board_id=? ORDER BY columns.position,cards.position,cards.id',(ident,))]
    return {'projectId':project_id,'revision':revision(db),'board':summary(db,row),'columns':columns,'cards':cards,'labels':[]}

def receipt(db,rid):
    row=db.execute('SELECT result FROM requests WHERE id=?',(rid,)).fetchone() if db else None
    if not row:raise ProjectFault('No original Board receipt exists for this request.',404)
    return json.loads(row[0])
