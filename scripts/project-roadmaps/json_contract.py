"""Strict portable JSON schema validation. Documents are data, never commands."""
from functools import lru_cache
import json
from pathlib import Path
import re
from storage import RoadmapFault

MAX_BYTES=16*1024*1024

@lru_cache(maxsize=1)
def schema():return json.loads((Path(__file__).resolve().parents[2]/'shared/roadmap-json.schema.json').read_text())

def validate(value):
    root=schema()
    def check(rule,value,path):
        if '$ref' in rule:rule=root['$defs'][rule['$ref'].removeprefix('#/$defs/')]
        if 'const' in rule and (type(value)!=type(rule['const']) or value!=rule['const']):raise RoadmapFault(path+': unexpected schema value.',400)
        if 'oneOf' in rule:
            matches=0;errors=[]
            for part in rule['oneOf']:
                try:check(part,value,path);matches+=1
                except RoadmapFault as error:errors.append(str(error))
            if matches!=1:
                chosen=next((p for p in rule['oneOf'] if p.get('properties',{}).get('scope',{}).get('const')==value.get('scope')),None) if isinstance(value,dict) else None
                if chosen:check(chosen,value,path)
                raise RoadmapFault(path+': expected exactly one portable document scope.',400)
        types=rule.get('type');types=[types] if isinstance(types,str) else types
        actual='null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'invalid'
        if types and actual not in types:raise RoadmapFault(path+': expected '+('/'.join(types))+'.',400)
        if 'enum' in rule and value not in rule['enum']:raise RoadmapFault(path+': invalid value.',400)
        if actual=='string':
            try:raw=value.encode('utf-8')
            except UnicodeError:raise RoadmapFault(path+': invalid UTF-8 text.',400) from None
            if not rule.get('minLength',0)<=len(value)<=rule.get('maxLength',32768) or len(raw)>rule.get('x-maxBytes',32768) or any(ord(c)<32 and c not in '\t\r\n' or ord(c)==127 for c in value):raise RoadmapFault(path+': text exceeds its field limit or contains control characters.',400)
            if 'pattern' in rule and not re.fullmatch(rule['pattern'],value):raise RoadmapFault(path+': invalid identity or number.',400)
        if actual=='integer' and not rule.get('minimum',0)<=value<=rule.get('maximum',2**53-1):raise RoadmapFault(path+': number outside its allowed range.',400)
        if actual=='array':
            if len(value)>rule.get('maxItems',10000):raise RoadmapFault(path+': too many entries.',413)
            if 'items' in rule:
                for i,item in enumerate(value):check(rule['items'],item,path+'['+str(i)+']')
        if actual=='object':
            props=rule.get('properties',{});missing=set(rule.get('required',[]))-value.keys();extra=value.keys()-props.keys() if rule.get('additionalProperties') is False else set()
            if missing or extra:raise RoadmapFault(path+': '+('missing '+', '.join(sorted(missing)) if missing else 'unexpected '+', '.join(sorted(extra)[:8]))+'.',400)
            for key,part in props.items():
                if key in value:check(part,value[key],path+'.'+key)
    check(root,value,'document')
    seen=set();count=0
    def identity(entry,path):
        nonlocal count
        if entry['id'] in seen:raise RoadmapFault(path+'.id: duplicate source identity.',400)
        seen.add(entry['id']);count+=1
        if count>20000:raise RoadmapFault('document exceeds 20000 entries.',413)
    def sub(entry,path,version=None):
        identity(entry,path)
        if version and (entry['versionId']!=version['id'] or entry['number'].rsplit('.',1)[0]!=version['number'][:-2]):raise RoadmapFault(path+': parent identity or version number disagrees.',400)
        for kind in ('tasks','acceptances'):
            for i,child in enumerate(entry[kind]):
                identity(child,path+'.'+kind+'['+str(i)+']')
                if child['subversionId']!=entry['id']:raise RoadmapFault(path+'.'+kind+'['+str(i)+'].subversionId: parent mismatch.',400)
        if entry.get('githubIssue') and entry['githubIssue']['acceptanceId'] not in {item['id'] for item in entry['acceptances']}:
            raise RoadmapFault(path+'.githubIssue.acceptanceId: acceptance does not belong to the source subversion.',400)
    def version(entry,path):
        identity(entry,path)
        for i,child in enumerate(entry['subversions']):sub(child,path+'.subversions['+str(i)+']',entry)
    data=value['data'];scope=value['scope']
    if scope=='roadmap':
        identity(data,'document.data')
        if data['id']!=value['source']['roadmapId'] or data['projectId']!=value['source']['projectId'] or data['currentVersionId']!=value['source']['currentVersionId'] or data['currentVersionId'] not in [v['id'] for v in data['versions']]:raise RoadmapFault('document.data: roadmap provenance or current version disagrees.',400)
        for i,child in enumerate(data['versions']):version(child,'document.data.versions['+str(i)+']')
    elif scope=='version':version(data,'document.data')
    else:sub(data,'document.data')
    return value

def parse(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:raise RoadmapFault('JSON file must contain 1 byte to 16 MiB.',413)
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('duplicate field')
            result[key]=value
        return result
    def invalid(_):raise ValueError('nonfinite number')
    try:value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)
    except (ValueError,UnicodeError,RecursionError):raise RoadmapFault('Upload one complete UTF-8 JSON document without duplicate fields or nonfinite numbers.',400) from None
    return validate(value)
