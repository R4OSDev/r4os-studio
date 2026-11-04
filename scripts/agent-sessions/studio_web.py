"""Explicit web service configuration and bounded, original Studio web reads."""
import asyncio
import fcntl
import hashlib
import http.client
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import socket
import ssl
from urllib.parse import urlsplit,urlunsplit,urlencode,urljoin
import uuid

from api_endpoint import endpoint,resolved_addresses
from profile import directory,regular,write_json
from session_store import identity,encode,now
from store import ProjectFault

MAX_BYTES=2*1024*1024


def search_endpoint(url):
    try:return endpoint(url,'custom')
    except ProjectFault:return endpoint(url,'local')


def settings(projects,data=None):
    parent=Path(projects)/'.studio';path=parent/'WebSearch.json'
    current=json.loads(regular(path).read_text()) if path.exists() else {'revision':1,'searchEndpoint':None,'requests':{}}
    if data is None:return {k:current[k] for k in ('revision','searchEndpoint')}
    if set(data)!={'requestId','revision','searchEndpoint'} or type(data['revision']) is not int:
        raise ProjectFault('Invalid web service settings.',400)
    rid=identity(data['requestId']);url=data['searchEndpoint']
    if url is not None:
        if not isinstance(url,str):raise ProjectFault('Use a SearXNG search endpoint or clear the service.',400)
        url=search_endpoint(url)['baseUrl']
    parent=directory(parent)
    fd=os.open(parent/'WebSearch.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=json.loads(regular(path).read_text()) if path.exists() else current
        fingerprint=hashlib.sha256(encode(data).encode()).hexdigest()
        old=current['requests'].get(rid)
        if old:
            if old['hash']!=fingerprint:raise ProjectFault('This request belongs to another web setting change.',409)
            return old['result']
        if current['revision']!=data['revision']:raise ProjectFault('Web settings changed. Read the current revision.',409)
        result={'revision':current['revision']+1,'searchEndpoint':url}
        requests=current['requests']|{rid:{'hash':fingerprint,'result':result}}
        write_json(path,{**result,'requests':requests})
        return result


def require(worker):
    if worker.config['engine'].get('kind')!='studio' or not worker.config.get('webSearchEnabled'):
        raise ProjectFault('Web access is disabled in this original run.',403)


class Text(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','template'):self.skip+=1
        elif tag in ('p','br','div','li','h1','h2','h3','tr'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','template') and self.skip:self.skip-=1
    def handle_data(self,value):
        if not self.skip:self.parts.append(value)


class Web:
    def __init__(self,worker):self.w=worker;self.connection=None;self.task=None;self.closing=False

    def fetch(self,url,configured=False):
        """No ambient proxy, cookie or provider credential is forwarded."""
        for _ in range(4):
            if self.closing or self.w.stopping:raise ProjectFault('The original web read was stopped.',409)
            if (not isinstance(url,str) or len(url.encode())>4096 or '\\' in url
                    or any(ord(c)<=32 or 127<=ord(c)<=159 for c in url)):raise ProjectFault('Use a public HTTP(S) page URL.',400)
            parsed=urlsplit(url)
            if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
                raise ProjectFault('Use a public HTTP(S) page URL without credentials.',400)
            host=parsed.hostname.encode('idna').decode('ascii');port=parsed.port or (443 if parsed.scheme=='https' else 80)
            addresses=[v[4][0] for v in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)]
            local=search_endpoint(urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'','')))['local'] if configured else False
            checked=resolved_addresses({'local':local},addresses)
            target=urlunsplit(('', '',parsed.path or '/',parsed.query,''))
            context=ssl.create_default_context()
            connection=http.client.HTTPSConnection(host,port,timeout=12,context=context) if parsed.scheme=='https' else http.client.HTTPConnection(host,port,timeout=12)
            def connect():
                raw=socket.create_connection((checked[0],port),12)
                try:
                    if self.closing or self.w.stopping:raise ProjectFault('The original web read was stopped before dispatch.',409)
                    connection.sock=context.wrap_socket(raw,server_hostname=host) if parsed.scheme=='https' else raw
                    if self.closing or self.w.stopping:connection.close();raise ProjectFault('The original web read was stopped before dispatch.',409)
                except BaseException:raw.close();raise
            connection.connect=connect
            self.connection=connection
            try:
                if self.closing or self.w.stopping:raise ProjectFault('The original web read was stopped.',409)
                connection.request('GET',target,headers={'User-Agent':'R4OS-Studio','Accept':'application/json,text/html,text/plain','Accept-Encoding':'identity'})
                response=connection.getresponse()
                if response.status in (301,302,303,307,308):
                    if configured:raise ProjectFault('Configure the direct search endpoint; redirects are not followed for service queries.',409)
                    location=response.getheader('Location')
                    if not location:raise ProjectFault('The page redirect has no target.',409)
                    url=urljoin(url,location);continue  # Each new target gets its own DNS check.
                if response.status!=200:raise ProjectFault('The web service returned HTTP'+str(response.status)+'. No alternate service was selected.',503)
                if response.getheader('Content-Encoding'):raise ProjectFault('This web response did not honor the uncompressed content contract.',503)
                media=response.headers.get_content_type()
                if media not in ('text/html','text/plain','application/json','application/xhtml+xml'):raise ProjectFault('This response is not a supported text page or search result.',415)
                raw=response.read(MAX_BYTES+1);truncated=len(raw)>MAX_BYTES;raw=raw[:MAX_BYTES]
                charset=response.headers.get_content_charset() or 'utf-8'
                if charset.lower() not in ('utf-8','utf8','us-ascii','ascii','iso-8859-1','latin1','windows-1252'):raise ProjectFault('This page uses an unsupported text encoding.',415)
                return {'url':url,'mediaType':media,'raw':raw,'text':raw.decode(charset,errors='replace'),'truncated':truncated}
            finally:
                connection.close()
                if self.connection is connection:self.connection=None
        raise ProjectFault('The page exceeded the redirect limit.',409)

    def root(self):return directory(self.w.store.directory/self.w.session_id/'WebResults')

    def retain(self,call_id,value):
        reference=str(uuid.uuid5(uuid.UUID(self.w.run_id),'web:'+call_id))
        raw=value.pop('raw');meta={**value,'reference':reference,'owner':{'type':self.w.store.owner_type,'id':self.w.store.owner_id},
            'sessionId':self.w.session_id,'runId':self.w.run_id,'createdAt':now(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        root=self.root();path=root/(reference+'.raw')
        if path.exists():
            if regular(path).read_bytes()!=raw:raise ProjectFault('The original web result changed.',409)
        else:
            with path.open('xb') as file:os.fchmod(file.fileno(),0o600);file.write(raw);file.flush();os.fsync(file.fileno())
        write_json(root/(reference+'.json'),meta)
        return meta

    def original(self,reference):
        reference=identity(reference);root=self.root();meta=json.loads(regular(root/(reference+'.json')).read_text())
        if meta['sessionId']!=self.w.session_id or meta['owner']!={'type':self.w.store.owner_type,'id':self.w.store.owner_id}:
            raise ProjectFault('This web result belongs to another session.',403)
        raw=regular(root/(reference+'.raw')).read_bytes()
        if len(raw)!=meta['bytes'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ProjectFault('The original web source changed.',409)
        return meta

    async def call(self,args,call_id):
        require(self.w)
        action=args['action'];value=None
        required={'search':('query',),'open':('url',),'find':('reference','pattern'),'read':('reference',)}
        if action not in required or any(key not in args for key in required[action]):raise ProjectFault('The web action is missing its original query, URL or reference.',400)
        if action in ('read','find'):value=self.original(args['reference'])
        else:
            if action=='search':
                service=(self.w.config.get('webService') or {}).get('searchEndpoint')
                if not service:return {'success':False,'error':'notConfigured','output':'No search service is configured. Page fetch remains available; no alternate search service was selected.'}
                url=service+'?'+urlencode({'q':args['query'],'format':'json'})
            else:url=args['url']
            task=asyncio.create_task(asyncio.to_thread(self.fetch,url,action=='search'));self.task=task
            try:value=await asyncio.shield(task)
            finally:
                if task.done() and self.task is task:self.task=None
            if action=='search':
                if value['truncated']:raise ProjectFault('The search result exceeded its bounded response size.',413)
                parsed=json.loads(value['text']);results=parsed.get('results')
                if not isinstance(results,list):raise ProjectFault('This configured service did not return SearXNG JSON results.',503)
                from web_search import public_url,text
                selected=[]
                for result in results:
                    if not isinstance(result,dict):continue
                    link=public_url(result.get('url'))
                    if link:selected.append({'url':link,'title':text(result.get('title'),256),'content':text(result.get('content'),4000)})
                    if len(selected)>=10:break
                value.update(text=encode({'kind':'untrusted_search_results','results':selected}),sources=[{'url':r['url'],'title':r['title']} for r in selected])
            elif value['mediaType'] in ('text/html','application/xhtml+xml'):
                parser=Text();parser.feed(value['text']);value['text']=''.join(parser.parts)
            value=self.retain(call_id,value)
        text=value['text'];offset=args.get('offset',0)
        if offset>len(text):raise ProjectFault('The requested web cursor exceeds the retained text.',400)
        if action=='find':
            pattern=args['pattern'];positions=[];at=0
            if not pattern:raise ProjectFault('Enter a nonempty search pattern.',400)
            while len(positions)<32:
                at=text.find(pattern,at)
                if at<0:break
                positions.append({'offset':at,'text':text[max(0,at-160):at+len(pattern)+160]});at+=len(pattern)
            content={'matches':positions,'matchLimit':32}
        else:
            content={'content':text[offset:offset+12000],'offset':offset,'nextOffset':offset+12000 if offset+12000<len(text) else None}
        output={'kind':'untrusted_web_data','reference':value['reference'],'url':value['url'] if action!='search' else None,
            'sha256':value['sha256'],'bytes':value['bytes'],'sourceTruncated':value['truncated'],'totalTextChars':len(text),**content}
        return {'success':True,'output':encode(output),'webSearch':{'action':'search' if action=='search' else 'findInPage' if action=='find' else 'openPage',
            **({'pattern':args['pattern']} if action=='find' else {}),
            **({'queries':[args['query']],'sources':value.get('sources',[])} if action=='search' else {'url':value['url']})}}

    async def close(self):
        self.closing=True
        if self.connection and self.connection.sock:
            try:self.connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.connection.close()
        if self.task:
            try:await asyncio.wait_for(asyncio.shield(self.task),15)
            except asyncio.TimeoutError:
                self.w.uncertain_effect=True;self.w.outcome='unknown';self.w.error='The original web read end could not be confirmed.'
            except BaseException:pass
