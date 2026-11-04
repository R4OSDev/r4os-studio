"""One shared skill broker for native Codex, Claude and API model transports."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import uuid
from skill_mcp_client import McpFault, atomic, directory, encoded, strict
import skill_runtime

PAGE = 49152


class SkillTools:
    def __init__(self, worker):
        self.worker = worker
        self.clients = {}
        self.catalogs = {}
        self.locks = {}

    def entry(self, ident):
        from skill_lifecycle import api
        from owner import skills_root
        entries = self.worker.config.get('skillAccess', {}).get('entries', [])
        value = next((e for e in entries if e['id'] == ident and e.get('mcp')), None)
        if not value or api.deleted(skills_root(self.worker.store.projects), ident):
            raise McpFault('This skill runtime is not enabled in the original accepted run.')
        return value

    async def catalog(self, entry):
        if entry['id'] not in self.catalogs:
            self.catalogs[entry['id']] = (await asyncio.to_thread(skill_runtime.load, self.worker, entry))[2]
        return self.catalogs[entry['id']]

    async def client(self, entry):
        if self.worker.stopping or not self.worker.lease:
            raise McpFault('The original active run no longer admits skill effects.')
        if entry['id'] not in self.clients:
            self.clients[entry['id']] = await skill_runtime.start(self.worker, entry)
        return self.clients[entry['id']]

    def root(self):
        return directory(self.worker.store.directory / self.worker.session_id / 'SkillMcpResults')

    def retain(self, entry, value, native_id, kind):
        ident = str(uuid.uuid5(uuid.UUID(self.worker.run_id), kind + ':' + native_id))
        raw = encoded(value)
        metadata = dict(schema=1, id=ident, ownerType=self.worker.store.owner_type, ownerId=self.worker.store.owner_id,
                        sessionId=self.worker.session_id, runId=self.worker.run_id, skillId=entry['id'],
                        packageHash=entry['activeHash'], sourceBinding=entry['mcp']['sourceBinding'], kind=kind,
                        sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        if kind=='nativeResult' and isinstance(value,dict):
            metadata['imageCount']=sum(isinstance(block,dict) and block.get('type')=='image' for block in value.get('content',[]))
        path = self.root() / (ident + '.json')
        if path.exists():
            if skill_runtime.runtime_spec.read(path) != raw: raise McpFault('The original skill result identity has different bytes.')
        else:
            atomic(path, raw)
            atomic(self.root() / (ident + '.metadata.json'), encoded(metadata))
        return metadata, raw

    def retained(self, entry, ident):
        if not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident): raise McpFault('Invalid original skill result reference.')
        root = self.root()
        metadata = strict(skill_runtime.runtime_spec.read(root / (ident + '.metadata.json')))
        if any(metadata.get(k) != v for k, v in dict(id=ident, ownerType=self.worker.store.owner_type,
                ownerId=self.worker.store.owner_id, sessionId=self.worker.session_id, skillId=entry['id']).items()):
            raise McpFault('This result belongs to a different skill, session or project.')
        raw = skill_runtime.runtime_spec.read(root / (ident + '.json'))
        if len(raw) != metadata['bytes'] or hashlib.sha256(raw).hexdigest() != metadata['sha256']:
            raise McpFault('The original skill result changed; it was not reconstructed or repeated.')
        return metadata, raw

    def page(self, metadata, raw, offset=0):
        if type(offset) is not int or not 0 <= offset <= len(raw): raise McpFault('The result offset is outside its original bytes.')
        try:
            prefix = raw[:offset].decode('utf-8')
            del prefix
        except UnicodeError: raise McpFault('Choose the returned UTF-8 byte cursor.') from None
        end = min(len(raw), offset + PAGE)
        while True:
            try: text = raw[offset:end].decode('utf-8'); break
            except UnicodeError: end -= 1
        value = dict(reference=metadata['id'], kind=metadata['kind'], sha256=metadata['sha256'], bytes=metadata['bytes'],
                     offset=offset, nextOffset=end if end < len(raw) else None, complete=end == len(raw),
                     originalRunId=metadata['runId'], originalPackageHash=metadata['packageHash'])
        value.update(sourceCommit=metadata['sourceBinding']['commit'],runtimeManifestHash=metadata['sourceBinding']['runtime']['manifestHash'])
        if offset == 0 and end == len(raw): value['payload'] = strict(raw)
        else: value.update(encoding='utf8-json-chunk', text=text)
        return dict(success=True, output=encoded(value).decode(), skillMcp=dict(skillId=metadata['skillId'],
                    packageHash=metadata['packageHash'], reference=metadata['id'], kind=metadata['kind'], sha256=metadata['sha256'],imageCount=metadata.get('imageCount',0)))

    async def discover(self, args, call_id):
        if not args.get('skillId'):
            entries = self.worker.config.get('skillAccess', {}).get('entries', [])
            return dict(success=True, output=encoded({'skills':[dict(id=e['id'],name=e['name'],tools=e['mcp']['tools'],
                        version=e['mcp']['sourceBinding']['runtime']['version']) for e in entries if e.get('mcp')]}).decode())
        entry = self.entry(args['skillId'])
        catalog = await self.catalog(entry)
        kind = args.get('kind','tools')
        if kind in ('tools','prompts'):
            values = catalog.get(kind, [])
        else:
            client = await self.client(entry)
            capability = 'resources'
            if capability not in client.capabilities: return dict(success=True, output=encoded(dict(kind=kind,items=[],available=False,reason='The native server does not advertise resources.')).decode())
            values = await client.listing('resources/templates/list' if kind=='resourceTemplates' else 'resources/list',
                                         'resourceTemplates' if kind=='resourceTemplates' else 'resources')
        if args.get('name') is not None:
            value = next((v for v in values if v.get('name',v.get('uri'))==args['name']),None)
            if value is None: raise McpFault('This item is absent from the complete frozen skill catalogue.')
            metadata, raw = self.retain(entry,value,call_id,'schema')
            return self.page(metadata,raw,args.get('schemaOffset',0))
        offset, limit = args.get('offset',0),args.get('limit',12)
        selected = values[offset:offset+limit]
        rows = [dict(name=v.get('name'),title=v.get('title'),descriptionPreview=v.get('description','')[:600],
                     **({'uri':v['uri']} if 'uri' in v else {})) for v in selected]
        return dict(success=True, output=encoded(dict(skillId=entry['id'],kind=kind,items=rows,total=len(values),offset=offset,
                    nextOffset=offset+len(selected) if offset+len(selected)<len(values) else None,
                    catalogueHash=entry['mcp']['catalogHash'],fullSchemas='Select an exact native name to read its complete schema.')).decode())

    async def invoke(self, args, call_id):
        entry = self.entry(args['skillId'])
        try: parameters = strict(args['argumentsJson'].encode())
        except (ValueError, UnicodeError): raise McpFault('argumentsJson must be strict JSON, retaining all original nulls, unions and fields.') from None
        if not isinstance(parameters,dict): raise McpFault('Native MCP arguments must be a JSON object.')
        permissions = self.worker.config['permissions']
        if not permissions.get('studio.exec_command') or not permissions.get('studio.read_file'):
            raise McpFault('Managed analysis requires Run command and Read file permissions.')
        client = await self.client(entry)
        if any(r['phase'] in ('unknown','cancel_requested') and r['method']=='tools/call' for r in client.receipts.values()):
            raise McpFault('An original analysis effect is still unconfirmed. Read its original receipt before another call.')
        rid = str(uuid.uuid5(uuid.UUID(self.worker.run_id),'skill-mcp:'+call_id))
        method, name = args.get('method','tools/call'),args.get('name')
        timeout = args.get('timeoutSeconds',120)
        if method=='tools/call':
            if not isinstance(name,str): raise McpFault('Choose an exact native tool name.')
            result = await client.call(name, parameters, request_id=rid, timeout=timeout)
        elif method=='prompts/get':
            if 'prompts' not in client.capabilities: raise McpFault('This server does not advertise prompts.')
            catalog = await self.catalog(entry)
            if name not in {p['name'] for p in catalog.get('prompts',[])}: raise McpFault('This prompt is absent from the frozen catalogue.')
            result = await client.request(method,dict(name=name,arguments=parameters),timeout=timeout,request_id=rid)
        elif method=='resources/read':
            if 'resources' not in client.capabilities or not isinstance(name,str): raise McpFault('This server does not advertise that resource operation.')
            if parameters: raise McpFault('Resource reads take their exact URI as name and argumentsJson={}.')
            result = await client.request(method,dict(uri=name),timeout=timeout,request_id=rid)
        elif method=='completion/complete':
            if 'completions' not in client.capabilities or name is not None: raise McpFault('Completion requires its advertised capability and unchanged full parameters without a name.')
            result = await client.request(method,parameters,timeout=timeout,request_id=rid)
        else: raise McpFault('Unsupported skill protocol operation.')
        metadata,raw = self.retain(entry,result,call_id,'nativeResult')
        value = self.page(metadata,raw)
        if isinstance(result,dict) and result.get('isError') is True:
            value.update(success=False,error='skillProviderError')
        return value

    async def call(self, name, args, call_id):
        try:
            if name=='skill_discover': return await self.discover(args,call_id)
            entry=self.entry(args['skillId'])
            if name=='read_skill_result':
                metadata,raw=self.retained(entry,args['reference'])
                return self.page(metadata,raw,args.get('offset',0))
            if name!='skill_call': raise McpFault('Unknown skill broker operation.')
            lock=self.locks.setdefault(entry['id'],asyncio.Lock())
            async with lock:return await self.invoke(args,call_id)
        except McpFault as error:
            unknown = bool(error.request_id and isinstance(error.state,dict) and not error.state.get('providerEndConfirmed',False))
            return dict(success=False,error='unknown' if unknown else 'skillUnavailable',output=str(error),
                        **({'partialChangesPossible':True,'skillMcpRequest':error.request_id} if unknown else {}))
        except (OSError,ValueError,KeyError,TypeError):
            return dict(success=False,error='skillUnavailable',output='The frozen skill runtime or original result is unavailable or changed. No alternate skill/runtime was selected.')

    def images(self, result):
        reference = result.get('skillMcp')
        if not reference or reference.get('kind')!='nativeResult': return []
        entry=self.entry(reference['skillId'])
        metadata,raw=self.retained(entry,reference['reference'])
        value=strict(raw)
        if not isinstance(value,dict):return []
        result=[];total=0
        for block in value.get('content',[]):
            if not isinstance(block,dict) or block.get('type')!='image':continue
            data=block.get('data');mime=block.get('mimeType')
            if not isinstance(data,str) or mime not in ('image/png','image/jpeg','image/webp'):continue
            total+=len(data)
            if total>12*1024*1024:break  # The complete original remains in the referenced result.
            try:base64.b64decode(data,validate=True)
            except ValueError:continue
            result.append(dict(type='image',data=data,mimeType=mime))
        return result

    async def close(self):
        if self.clients:
            ends=await asyncio.gather(*(client.close() for client in self.clients.values()),return_exceptions=True)
            if any(isinstance(value,BaseException) or not value.get('processEndConfirmed') for value in ends):
                self.worker.uncertain_effect=True
                self.worker.outcome='unknown'
                self.worker.error=self.worker.error or 'A managed skill process end remains unconfirmed.'
