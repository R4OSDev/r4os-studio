"""Explicit human archive/restore/delete; never infer another entity's state."""
from board_model import card_row
from board_validation import fields,identity,integer
from store import ProjectFault

def apply(db,bid,action,data,stamp):
    if action in ('archive_card','restore_card'):
        fields(data,('cardId','expectedCardRevision'));row=card_row(db,bid,identity(data['cardId']))
        if row['revision']!=integer(data['expectedCardRevision']):raise ProjectFault('This card changed. Review it before changing its archive state.',409)
        target=int(action=='archive_card')
        if row['archived']==target:raise ProjectFault('This card archive state already changed. Refresh the Board.',409)
        db.execute('UPDATE cards SET archived=?,revision=revision+1,updated_at=? WHERE id=?',(target,stamp,row['id']))
        result={'cardId':row['id'],'cardArchived':bool(target)}
    elif action=='delete_board':
        fields(data,('confirm',))
        if data['confirm'] is not True:raise ProjectFault('Confirm permanently deleting this Board and all its cards.',400)
        db.execute('DELETE FROM boards WHERE id=?',(bid,))
        for position,row in enumerate(db.execute('SELECT id FROM boards ORDER BY position,id').fetchall()):db.execute('UPDATE boards SET position=? WHERE id=?',(position,row['id']))
        result={'boardDeleted':True}
    else:
        fields(data);target=int(action=='archive_board')
        row=db.execute('SELECT archived FROM boards WHERE id=?',(bid,)).fetchone()
        if row['archived']==target:raise ProjectFault('This Board archive state already changed. Refresh the list.',409)
        db.execute('UPDATE boards SET archived=? WHERE id=?',(target,bid));result={'boardArchived':bool(target)}
    db.execute('UPDATE meta SET feature_level=MAX(feature_level,4) WHERE singleton=1')
    return result
