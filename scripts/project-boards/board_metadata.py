"""Explicit user edits to card metadata/checklists and board-scoped labels."""
import datetime
import uuid
from board_model import card_row
from board_validation import fields,identity,integer,text,name_key,COLORS,MAX_LABELS,MAX_CHECKLIST
from store import ProjectFault

def calendar(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)!=10:raise ProjectFault('Use a calendar date in YYYY-MM-DD format.',400)
    try:
        if datetime.date.fromisoformat(value).isoformat()!=value:raise ValueError()
    except ValueError:raise ProjectFault('Invalid calendar date.',400) from None
    return value

def label(db,bid,ident):
    row=db.execute('SELECT * FROM labels WHERE board_id=? AND id=?',(bid,identity(ident))).fetchone()
    if not row:raise ProjectFault('Label not found in this Board.',404)
    return row

def edit_card(db,bid,data,stamp):
    fields(data,('cardId','expectedCardRevision'),('title','description','priority','dueDate','labelIds','checklist'))
    row=card_row(db,bid,identity(data['cardId']))
    if row['revision']!=integer(data['expectedCardRevision']):raise ProjectFault('This card changed. Your draft was preserved; review its saved details.',409)
    if not set(data)&{'title','description','priority','dueDate','labelIds','checklist'}:raise ProjectFault('Choose a card field to change.',400)
    title=text(data.get('title',row['title']),240);description=text(data.get('description',row['description']),16000,True,True)
    priority=data.get('priority',row['priority'])
    if priority not in ('low','normal','high'):raise ProjectFault('Choose Low, Normal or High priority.',400)
    due=calendar(data.get('dueDate',row['due_date']))
    if 'labelIds' in data:
        ids=data['labelIds']
        if not isinstance(ids,list) or len(ids)>MAX_LABELS:raise ProjectFault('Invalid card labels.',400)
        for ident in ids:label(db,bid,ident)
        if len(ids)!=len(set(ids)):raise ProjectFault('Duplicate card labels.',400)
        db.execute('DELETE FROM card_labels WHERE card_id=?',(row['id'],))
        db.executemany('INSERT INTO card_labels VALUES(?,?,?)',[(bid,row['id'],ident) for ident in ids])
    if 'checklist' in data:
        checks=data['checklist']
        if not isinstance(checks,list) or len(checks)>MAX_CHECKLIST:raise ProjectFault('Keep at most100 checklist items per card.',400)
        old={r['id']:r for r in db.execute('SELECT * FROM checklist WHERE card_id=?',(row['id'],))};seen=set();prepared=[]
        for position,item in enumerate(checks):
            fields(item,('id','text','checked','revision'));ident=identity(item['id']);revision=integer(item['revision'],0);content=text(item['text'],240)
            if ident in seen or type(item['checked']) is not bool:raise ProjectFault('Invalid checklist item.',400)
            seen.add(ident);previous=old.get(ident)
            if previous:
                if previous['revision']!=revision:raise ProjectFault('A checklist item changed. Review the saved card.',409)
            elif revision!=0 or db.execute('SELECT 1 FROM checklist WHERE id=?',(ident,)).fetchone():raise ProjectFault('A checklist item was removed or belongs to another card. Remove it from this draft before saving.',409)
            prepared.append((ident,content,item['checked'],position,previous))
        for ident in old.keys()-seen:db.execute('DELETE FROM checklist WHERE id=?',(ident,))
        for ident,content,checked,position,previous in prepared:
            if previous:
                if (previous['text'],previous['checked'],previous['position'])!=(content,int(checked),position):db.execute('UPDATE checklist SET text=?,checked=?,position=?,revision=revision+1 WHERE id=?',(content,int(checked),position,ident))
            else:db.execute('INSERT INTO checklist(id,board_id,card_id,text,checked,position) VALUES(?,?,?,?,?,?)',(ident,bid,row['id'],content,int(checked),position))
    if set(data)&{'priority','dueDate','labelIds','checklist'}:db.execute('UPDATE meta SET feature_level=MAX(feature_level,3) WHERE singleton=1')
    db.execute('UPDATE cards SET title=?,description=?,priority=?,due_date=?,revision=revision+1,updated_at=? WHERE id=?',(title,description,priority,due,stamp,row['id']))
    return {'cardId':row['id']}

def edit_label(db,bid,action,data,stamp):
    if action=='create_label':
        fields(data,('name','color'));ident=str(uuid.uuid4())
        if db.execute('SELECT COUNT(*) FROM labels WHERE board_id=?',(bid,)).fetchone()[0]>=MAX_LABELS:raise ProjectFault('This Board reached its label limit.',409)
    else:
        fields(data,('labelId','expectedLabelRevision','confirm') if action=='delete_label' else ('labelId','expectedLabelRevision','name','color'))
        row=label(db,bid,data['labelId']);ident=row['id']
        if row['revision']!=integer(data['expectedLabelRevision']):raise ProjectFault('This label changed. Review the saved label.',409)
    if action=='delete_label':
        if data['confirm'] is not True:raise ProjectFault('Confirm removing this label from its cards.',400)
        affected=[r[0] for r in db.execute('SELECT card_id FROM card_labels WHERE label_id=?',(ident,))]
        db.executemany('UPDATE cards SET revision=revision+1,updated_at=? WHERE id=?',[(stamp,cid) for cid in affected])
        db.execute('DELETE FROM labels WHERE id=?',(ident,))
    else:
        name=text(data['name'],64);color=data['color']
        if color not in COLORS:raise ProjectFault('Choose a Studio label color.',400)
        if db.execute('SELECT 1 FROM labels WHERE board_id=? AND name_key=? AND id!=?',(bid,name_key(name),ident)).fetchone():raise ProjectFault('A label with this name already exists in this Board.',409)
        if action=='create_label':db.execute('INSERT INTO labels(id,board_id,name,name_key,color) VALUES(?,?,?,?,?)',(ident,bid,name,name_key(name),color))
        else:db.execute('UPDATE labels SET name=?,name_key=?,color=?,revision=revision+1 WHERE id=?',(name,name_key(name),color,ident))
    db.execute('UPDATE meta SET feature_level=MAX(feature_level,3) WHERE singleton=1')
    return {'labelId':ident,'labelRemoved':action=='delete_label'}
