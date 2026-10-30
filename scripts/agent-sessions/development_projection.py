"""Small v15 presentations; original jobs, receipts, inventories and logs stay intact."""
import base64
import hashlib
import json
from contracts import DevelopmentFault

LIMIT_BYTES = 12288
FRAGMENT_JSON_BYTES = 6000


def encoded(value): return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def short(value,maximum=300):
    return value[:maximum] if isinstance(value,str) else value


def pick(value,keys): return {k:value[k] for k in keys if k in value}


def fragment(text):
    """Size the serialized string, retaining complete Unicode codepoints."""
    low,high=0,min(len(text),FRAGMENT_JSON_BYTES)
    while low<high:
        middle=(low+high+1)//2
        if len(encoded(text[:middle]).encode())<=FRAGMENT_JSON_BYTES:low=middle
        else:high=middle-1
    return text[:low]


def output_state(page):
    return {**pick(page,('startOffset','nextOffset','pageBytes','totalBytes','hasMore','outputKind','outputEncoding','truncated','captureLimitReached','captureTruncated')),
        'nativeOutputComplete': ((page.get('executionEvidence') or {}).get('output',{}).get('state')=='complete') if (page.get('job') or {}).get('kind')=='execution' else None}


def summary(job,page=None):
    page=page or {};small=pick(job,('id','projectId','kind','state','phase','revision','artifactId','deploymentId','exitCode','createdAt','completedAt','reasonCode'))
    small['error']=short(job.get('error'),512)
    for key in ('process','desktopLaunchBudget'):
        if isinstance(job.get(key),dict):small[key]=job[key]
    if job.get('checkCompletion'):small['checkCompletion']=pick(job['checkCompletion'],('requestId','reason','state','cancelled','closed','completedAt'))
    if job.get('recovery'):small['recovery']=pick(job['recovery'],('id','source','replayed','guestEndConfirmed'))
    if job.get('target'):small['target']=pick(job['target'],('vmId','bootId'))
    if job.get('source'):small['source']=pick(job['source'],('id','sha256','manifestSha256'))
    if job.get('pins'):small['pinsSha256']=hashlib.sha256(encoded(job['pins']).encode()).hexdigest()
    if job.get('readiness'):
        small['readiness']=pick(job['readiness'],('state','reasonCode','checkedAt','desktopEvidence'))
        small['readiness']['reason']=short(job['readiness'].get('reason'))
    if job.get('check'):
        check=job['check'];small['check']=pick(check,('state','assessment'))
        small['check']['findings']=[short(v,200) for v in check.get('findings',[])[:4]]
        small['check']['evidenceIds']=check.get('evidenceIds',[])[:8]
        small['check']['criteriaDetails']='Read view=details; all configured criteria remain unchanged.'
    if job.get('desktopLaunch'):small['desktopLaunch']=pick(job['desktopLaunch'],('request','phase','errorlevel','content','window','process_id','process_generation','statusErrorlevel'))
    if job.get('outputFiles') is not None:
        small['outputFiles']=[{**pick(v,('name','state','id','sha256','bytes','containsExpectedText')),
            **({'error':short(v['error'],160)} if v.get('error') else {})} for v in job['outputFiles'][:8]]
    if job.get('liveFileObservation'):small['liveFileObservation']=pick(job['liveFileObservation'],('checkedAt','mode','completionConfirmed'))
    artifact=page.get('artifact') or {}
    value={'job':small,'presentation':{'version':1,'limitBytes':LIMIT_BYTES,'detailsOmitted':True,
        'read':{'jobId':job['id'],'views':['details','inventory','output']},
        'notice':'Presentation summary only. Omitted details and saved log pages are retained; no action was replayed.'}}
    if page.get('artifactSummary'):value['artifact']=page['artifactSummary']
    if page.get('artifactUnavailable'):value['artifactUnavailable']=page['artifactUnavailable']
    if artifact:
        value['artifact']={**pick(artifact,('id','entry','packageSha256','sourceSha256','manifestSha256','buildProof')),
            'fileCount':len(artifact.get('files',[])), 'inventoryView':'inventory'}
    if page.get('executionEvidence'):value['executionEvidence']=page['executionEvidence']
    if page.get('stop'):value['stop']=page['stop']
    value['outputPage']=output_state(page)
    # A preview consumes no cursor. Explicit output begins at the original requested offset.
    if page.get('output'):value['outputPreview']={'text':fragment(page['output'][:500]),'consumesCursor':False}
    if len(encoded(value).encode())>LIMIT_BYTES:
        value={'job':pick(small,('id','projectId','kind','state','phase','revision','artifactId','deploymentId','exitCode','reasonCode')),
            'presentation':value['presentation'],'outputPage':value['outputPage'],
            'check':pick(small.get('check',{}),('state','assessment')),'checkCompletion':small.get('checkCompletion'),
            'readiness':pick(small.get('readiness',{}),('state','reasonCode')),
            'notice':'Detailed checks, artifacts and cleanup receipts are retained in view=details.'}
    return value


def view(page,kind,cursor=None,offset=0):
    job=page['job'];binding={'jobId':job['id'],'view':kind,'revision':job['revision']}
    if kind=='output':
        if cursor:raise DevelopmentFault('Output uses nextOffset, not a detail cursor.',400)
        if page.get('rawOutputBase64'):
            raw=base64.b64decode(page['rawOutputBase64'],validate=True);end=min(len(raw),4000)
            for start in range(max(0,end-3),end):
                lead=raw[start];width=2 if 0xc2<=lead<=0xdf else 3 if 0xe0<=lead<=0xef else 4 if 0xf0<=lead<=0xf4 else 0
                if width and start<end<start+width:
                    try:raw[start:start+width].decode('utf-8')
                    except UnicodeDecodeError:continue
                    end=start;break
            raw=raw[:end]
            content={'encoding':'base64','data':base64.b64encode(raw).decode()};count=len(raw)
        else:
            text=fragment(page.get('output',''));content={'encoding':'utf-8','text':text};count=len(text.encode())
        return {**binding,'output':content,**output_state(page),'startOffset':offset,'pageBytes':count,'nextOffset':offset+count,
            'hasMore':offset+count<page.get('totalBytes',offset+count),'jobState':job['state'],
            'mayGrow':job['state'] in ('queued','starting','running','stopping'),'detailsOmitted':False}
    if kind not in ('details','inventory'):raise DevelopmentFault('Unknown development presentation view.',400)
    body={k:v for k,v in page.items() if k not in ('output','rawOutputBase64','artifact')}
    if kind=='inventory':body={'jobId':job['id'],'revision':job['revision'],'artifact':page.get('artifact'),
        'source':job.get('source'),'pins':job.get('pins'),'outputFiles':job.get('outputFiles'),'evidence':page.get('evidence',[])}
    raw=encoded(body).encode();digest=hashlib.sha256(raw).hexdigest();position=0
    if cursor:
        try:
            current=json.loads(base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4)))
            if (not isinstance(current,dict) or any(current.get(k)!=v for k,v in {**binding,'sha256':digest}.items())
                or type(current.get('offset')) is not int or not 0<current['offset']<len(raw)):raise ValueError()
            position=current['offset'];raw[position:].decode('utf-8')
        except (ValueError,TypeError,UnicodeError):raise DevelopmentFault('The original detail snapshot changed or the cursor belongs to another job/view. Read its first page again; no action was replayed.',409) from None
    text=fragment(raw[position:].decode('utf-8'));end=position+len(text.encode())
    next_cursor=base64.urlsafe_b64encode(encoded({**binding,'sha256':digest,'offset':end}).encode()).decode().rstrip('=') if end<len(raw) else None
    return {**binding,'snapshotSha256':digest,'encoding':'utf-8-json','fragment':text,'startOffset':position,
        'nextOffset':end,'totalBytes':len(raw),'hasMore':end<len(raw),'nextCursor':next_cursor,'detailsOmitted':False}
