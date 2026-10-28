"""Narrow parent-bound column/card actions inside the original receipt transaction."""
import uuid
from board_model import column,card_row
from board_validation import fields,identity,integer,text,MAX_COLUMNS,MAX_CARDS
from store import ProjectFault

ACTIONS=('create_column','update_column','delete_column','create_card','update_card','delete_card','move_card','move_column','create_label','update_label','delete_label')

def normalize(db,table,parent_key,parent):
    for position,row in enumerate(db.execute('SELECT id,position FROM '+table+' WHERE '+parent_key+'=? ORDER BY position,id',(parent,)).fetchall()):
        if row['position']!=position:db.execute('UPDATE '+table+' SET position=?,revision=revision+1 WHERE id=?',(position,row['id']))

def apply(db,bid,action,data,stamp):
    result={};reordered=False
    if action=='create_column':
        fields(data,('title',));title=text(data['title'])
        count=db.execute('SELECT COUNT(*) FROM columns WHERE board_id=?',(bid,)).fetchone()[0]
        if count>=MAX_COLUMNS:raise ProjectFault('This Board reached its column limit.',409)
        ident=str(uuid.uuid4());db.execute('INSERT INTO columns(id,board_id,title,position) VALUES(?,?,?,?)',(ident,bid,title,count))
        result['columnId']=ident;reordered=True
    elif action in ('update_column','delete_column'):
        fields(data,('columnId','expectedColumnRevision','title') if action=='update_column' else ('columnId','expectedColumnRevision','confirm'),('targetColumnId',) if action=='delete_column' else ())
        source=column(db,bid,identity(data['columnId']))
        if source['revision']!=integer(data['expectedColumnRevision']):raise ProjectFault('This column changed. Reload before saving.',409)
        if action=='update_column':db.execute('UPDATE columns SET title=?,revision=revision+1 WHERE id=?',(text(data['title']),source['id']))
        else:
            if data['confirm'] is not True:raise ProjectFault('Confirm removing this column.',400)
            if db.execute('SELECT COUNT(*) FROM columns WHERE board_id=?',(bid,)).fetchone()[0]<=1:raise ProjectFault('Keep at least one column in this Board.',409)
            rows=db.execute('SELECT id FROM cards WHERE board_id=? AND column_id=? ORDER BY position,id',(bid,source['id'])).fetchall()
            target=column(db,bid,identity(data['targetColumnId'])) if data.get('targetColumnId') else None
            if target and target['id']==source['id']:raise ProjectFault('Choose a different target column.',400)
            if rows:
                if not target:raise ProjectFault('Choose a column in this Board for every existing card before removing its column.',400)
                start=db.execute('SELECT COUNT(*) FROM cards WHERE board_id=? AND column_id=?',(bid,target['id'])).fetchone()[0]
                for index,row in enumerate(rows):db.execute('UPDATE cards SET column_id=?,position=?,revision=revision+1,updated_at=? WHERE id=?',(target['id'],start+index,stamp,row['id']))
            db.execute('DELETE FROM columns WHERE id=?',(source['id'],));normalize(db,'columns','board_id',bid)
            result.update(deleted=True,movedCards=len(rows));reordered=True
        result['columnId']=source['id']
    elif action=='create_card':
        fields(data,('columnId','title'),('description',));target=column(db,bid,identity(data['columnId']))
        if db.execute('SELECT COUNT(*) FROM cards WHERE board_id=?',(bid,)).fetchone()[0]>=MAX_CARDS:raise ProjectFault('This Board reached its card limit.',409)
        title=text(data['title'],240);description=text(data.get('description',''),16000,True,True);ident=str(uuid.uuid4())
        position=db.execute('SELECT COUNT(*) FROM cards WHERE board_id=? AND column_id=?',(bid,target['id'])).fetchone()[0]
        db.execute('UPDATE meta SET feature_level=MAX(feature_level,2) WHERE singleton=1')
        db.execute('INSERT INTO cards(id,board_id,column_id,title,description,position,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(ident,bid,target['id'],title,description,position,stamp,stamp))
        result['cardId']=ident;reordered=True
    elif action=='update_card':
        from board_metadata import edit_card
        result=edit_card(db,bid,data,stamp)
    elif action=='delete_card':
        fields(data,('cardId','expectedCardRevision'),('confirm',))
        row=card_row(db,bid,identity(data['cardId']))
        if row['revision']!=integer(data['expectedCardRevision']):raise ProjectFault('This card changed. Your draft was preserved; reload before saving.',409)
        if data.get('confirm') is not True:raise ProjectFault('Confirm permanently deleting this card.',400)
        db.execute('DELETE FROM cards WHERE id=?',(row['id'],));normalize(db,'cards','column_id',row['column_id'])
        result['deleted']=True;reordered=True
        result['cardId']=row['id']
    elif action in ('move_card','move_column'):
        from board_moves import apply as move
        result,reordered=move(db,bid,action,data,stamp)
    elif action in ('create_label','update_label','delete_label'):
        from board_metadata import edit_label
        result=edit_label(db,bid,action,data,stamp)
    else:raise ProjectFault('Unsupported Board entry action.',400)
    db.execute('UPDATE boards SET revision=revision+1,order_revision=order_revision+?,updated_at=? WHERE id=?',(int(reordered),stamp,bid))
    return result
