"""Visible, deterministic add/update mapping; source IDs never grant authority."""
import json
import uuid
from model import common
from reads import root_row
from storage import RoadmapFault
from validation import fields,identity,integer,target

MAX_ENTRIES=20000

def plan(db,project_id,preview_id,document,body):
    scope=document['scope'];mode=body['mode'];reference=body['target'];data=document['data']
    if mode not in ('add','update'):raise RoadmapFault('mode must be add or update.',400)
    if not isinstance(reference,dict) or reference.get('kind')!=scope:raise RoadmapFault('target.kind must match the complete JSON document scope.',400)
    fields(reference,['kind'],['id','versionId'])
    root=root_row(db)
    if scope=='roadmap':
        if reference.get('id')!=root['id'] or 'versionId' in reference:raise RoadmapFault('Select this project roadmap root as target.',409)
    elif scope=='version':
        if 'versionId' in reference:raise RoadmapFault('A version import targets a main version, not a parent versionId.',400)
        if 'id' in reference:target(db,reference)
        if mode=='add' and 'id' in reference:raise RoadmapFault('Add mode creates a new version; omit target.id.',400)
    else:
        if 'versionId' not in reference:raise RoadmapFault('target.versionId is required for a subversion import.',400)
        target(db,reference,needs_id='id' in reference)
        if mode=='add' and 'id' in reference:raise RoadmapFault('Add mode creates a new subversion; omit target.id.',400)
    policy=body.get('numberPolicy','preserve')
    if policy not in ('preserve','next') or policy=='next' and (scope!='subversion' or mode!='add'):raise RoadmapFault('numberPolicy=next is available only when adding a subversion.',400)
    operations=[];create_ids={};placements=[];mapping=[];changes=[];conflicts=[]
    def change(kind,entry,ref,existing,number=None):
        allowed=('description','notes') if kind=='roadmap' else ('title','vision','notes','status') if kind=='version' else ('title','description','notes','status') if kind=='subversion' else ('description','notes','status')
        value={k:entry[k] for k in allowed}
        if kind in ('version','subversion'):value['number']=number or entry['number']
        source = entry.get('githubIssue') if kind == 'subversion' else None
        if source and source['url'] not in value.get('notes', ''):
            notes = value.get('notes', '')
            suffix = f'\nGitHub Issue #{source["number"]}\n{source["url"]}'
            if len((notes + suffix).encode()) <= 32768:
                value['notes'] = (notes + suffix).lstrip('\n')
        if existing is not None:
            ident=existing['id'];ref={**ref,'id':ident};action='update';key=None
        else:
            ident=str(uuid.uuid5(uuid.UUID(preview_id),kind+':'+entry['id']));action='create';key='n'+str(len(operations));create_ids[str(len(operations))]=ident
        op={'action':action,'target':ref,'input':value}
        if key:op['key']=key
        operations.append(op)
        mapping.append({'kind':kind,'sourceId':entry['id'],'targetId':ident,'action':action,**({'sourceNumber':entry['number'],'targetNumber':value['number']} if kind in ('version','subversion') else {})})
        changes.append({'kind':kind,'sourceId':entry['id'],'targetId':ident,'action':action,'fields':list(value),
                        'before':{k:existing[k] for k in allowed} if existing is not None else None,'after':value})
        if existing is not None and kind in ('version','subversion'):
            previous=(f'{existing["major"]}.{existing["minor"]}.X' if kind=='version' else str(db.execute('SELECT major FROM versions WHERE id=?',(existing['version_id'],)).fetchone()[0])+'.'+str(db.execute('SELECT minor FROM versions WHERE id=?',(existing['version_id'],)).fetchone()[0])+'.'+str(existing['patch']))
            changes[-1]['before']['number']=previous;mapping[-1]['previousNumber']=previous
        if kind!='roadmap':
            order=entry['order']
            if existing is None and mode=='add' and kind in ('version','subversion'):
                table='versions' if kind=='version' else 'subversions';parent_key='roadmap_id' if kind=='version' else 'version_id';parent_id=root['id'] if kind=='version' else ref['versionId']
                offset=db.execute('SELECT coalesce(max(position),-1)+1 FROM '+table+' WHERE '+parent_key+'=?',(parent_id,)).fetchone()[0];order+=offset
            placements.append({'kind':kind,'id':ident,'order':order});mapping[-1].update(sourceOrder=entry['order'],targetOrder=order)
        return ident,'$'+key if key else ident
    def items(kind,entries,parent_id,parent_ref,version_ref):
        table='tasks' if kind=='task' else 'acceptances';seen=set()
        for entry in entries:
            if entry['order'] in seen:conflicts.append('Duplicate '+kind+' position '+str(entry['order'])+' in source subversion.');continue
            seen.add(entry['order']);rows=list(db.execute('SELECT * FROM '+table+' WHERE subversion_id=? AND position=?',(parent_id,entry['order']))) if mode=='update' else []
            if len(rows)>1:conflicts.append('Ambiguous '+kind+' target position '+str(entry['order'])+'.');continue
            existing=rows[0] if rows else None
            change(kind,entry,{'kind':kind,'versionId':version_ref,'subversionId':parent_ref},existing)
    def subversion(entry,version_id,version_ref,version_number,explicit=None):
        patch=int(entry['number'].rsplit('.',1)[1]);number=version_number[:-1]+str(patch)
        if policy=='next':
            patch=db.execute('SELECT coalesce(max(patch),0)+1 FROM subversions WHERE version_id=?',(version_id,)).fetchone()[0];number=version_number[:-1]+str(patch)
        existing=explicit or db.execute('SELECT * FROM subversions WHERE version_id=? AND patch=?',(version_id,patch)).fetchone()
        if mode=='add' and existing is not None:conflicts.append('Subversion '+number+' already exists; choose Update or the next available number.');return
        ident,ref=change('subversion',entry,{'kind':'subversion','versionId':version_ref},existing,number)
        items('task',entry['tasks'],ident,ref,version_ref);items('acceptance',entry['acceptances'],ident,ref,version_ref)
    def version(entry,explicit=None):
        major,minor,_=entry['number'].split('.')
        if explicit is not None and (explicit['major'],explicit['minor'])!=(int(major),int(minor)):
            conflicts.append('The selected main version has a different number. Import as a new version or match its existing number; import does not renumber omitted children.');return
        existing=explicit or db.execute('SELECT * FROM versions WHERE major=? AND minor=?',(int(major),int(minor))).fetchone()
        if mode=='add' and existing is not None:conflicts.append('Version '+entry['number']+' already exists; choose Update or a distinct version number.');return
        ident,ref=change('version',entry,{'kind':'version'},existing)
        seen=set()
        for sub in entry['subversions']:
            number=sub['number']
            if number in seen:conflicts.append('Duplicate subversion number '+number+'.');continue
            seen.add(number);subversion(sub,ident,ref,entry['number'])
    if scope=='roadmap':
        if mode=='update':change('roadmap',data,{'kind':'roadmap'},root)
        seen=set()
        for entry in data['versions']:
            if entry['number'] in seen:conflicts.append('Duplicate version number '+entry['number']+'.');continue
            seen.add(entry['number']);version(entry)
    elif scope=='version':version(data,target(db,reference) if 'id' in reference else None)
    else:
        parent=target(db,{'kind':'version','id':reference['versionId']});subversion(data,parent['id'],parent['id'],f'{parent["major"]}.{parent["minor"]}.X',target(db,reference) if 'id' in reference else None)
    if len(operations)>MAX_ENTRIES:raise RoadmapFault('Import plan exceeds 20000 operations.',413)
    if not operations and not conflicts:conflicts.append('The selected scope contains no changes to import.')
    return {'operations':operations,'createIds':create_ids,'placements':placements,'mapping':mapping,'changes':changes,'conflicts':conflicts,
            'counts':{'create':sum(v['action']=='create' for v in mapping),'update':sum(v['action']=='update' for v in mapping),'delete':0},
            'matching':'Version/subversion numbers and task/acceptance positions under the confirmed target parents. Source UUIDs are provenance, not authorization.',
            'currentVersionChanged':False,'archiveReferencesIgnored':len(document['archiveReferences'])}

def apply(db,plan,now):
    from batches import apply_operations
    result=apply_operations(db,plan['operations'],now,MAX_ENTRIES,plan['createIds'],True)
    tables={'version':'versions','subversion':'subversions','task':'tasks','acceptance':'acceptances'}
    for entry in plan['placements']:
        integer(entry['order'],0,2147483647);identity(entry['id']);table=tables[entry['kind']]
        cursor=db.execute('UPDATE '+table+' SET position=? WHERE id=?',(entry['order'],entry['id']))
        if cursor.rowcount!=1:raise RoadmapFault('An original import placement is unavailable.',409)
    return result

def validate(db,value,now):
    import sqlite3
    clone=sqlite3.connect(':memory:')
    try:
        clone.deserialize(db.serialize());clone.row_factory=sqlite3.Row;clone.execute('PRAGMA foreign_keys=ON');apply(clone,value,now)
        if clone.execute('PRAGMA foreign_key_check').fetchone():raise RoadmapFault('Import contains an invalid parent binding.',400)
    finally:clone.close()
