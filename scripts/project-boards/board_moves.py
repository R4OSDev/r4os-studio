"""Move one original entity; never accept a filtered replacement inventory."""
from board_model import column,card_row
from board_validation import fields,identity,integer
from store import ProjectFault

def apply(db,bid,action,data,stamp):
    if action=='move_column':
        fields(data,('columnId','expectedColumnRevision','position'))
        source=column(db,bid,identity(data['columnId']))
        if source['revision']!=integer(data['expectedColumnRevision']):raise ProjectFault('The original column changed. Review the current order.',409)
        rows=db.execute('SELECT id,position FROM columns WHERE board_id=? ORDER BY position,id',(bid,)).fetchall()
        ids=[r['id'] for r in rows if r['id']!=source['id']];position=integer(data['position'],0,len(ids));ids.insert(position,source['id'])
        changed=ids!=[r['id'] for r in rows]
        for index,ident in enumerate(ids):
            row=next(r for r in rows if r['id']==ident)
            if row['position']!=index:db.execute('UPDATE columns SET position=?,revision=revision+1 WHERE id=?',(index,ident))
        return {'columnId':source['id'],'unchanged':not changed},changed
    fields(data,('cardId','expectedCardRevision','sourceColumnId','targetColumnId','position'))
    source=card_row(db,bid,identity(data['cardId']));source_column=identity(data['sourceColumnId'])
    if source['revision']!=integer(data['expectedCardRevision']) or source['column_id']!=source_column:
        raise ProjectFault('The original card or source column changed. Review its current position.',409)
    target=column(db,bid,identity(data['targetColumnId']))
    rows=db.execute('SELECT id,position FROM cards WHERE board_id=? AND column_id=? ORDER BY position,id',(bid,target['id'])).fetchall()
    ids=[r['id'] for r in rows if r['id']!=source['id']];position=integer(data['position'],0,len(ids));ids.insert(position,source['id'])
    changed=source_column!=target['id'] or ids!=[r['id'] for r in rows]
    if changed:
        db.execute('UPDATE cards SET column_id=?,position=?,revision=revision+1,updated_at=? WHERE id=?',(target['id'],position,stamp,source['id']))
        for index,ident in enumerate(ids):
            if ident==source['id']:continue
            row=next(r for r in rows if r['id']==ident)
            if row['position']!=index:db.execute('UPDATE cards SET position=?,revision=revision+1,updated_at=? WHERE id=?',(index,stamp,ident))
        if source_column!=target['id']:
            for index,row in enumerate(db.execute('SELECT id,position FROM cards WHERE board_id=? AND column_id=? ORDER BY position,id',(bid,source_column)).fetchall()):
                if row['position']!=index:db.execute('UPDATE cards SET position=?,revision=revision+1,updated_at=? WHERE id=?',(index,stamp,row['id']))
    return {'cardId':source['id'],'unchanged':not changed},changed
