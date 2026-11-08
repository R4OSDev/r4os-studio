"""Real namespaces and broker bindings against a small explicit MCP fixture."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
import uuid
from skill_mcp_client import encoded
from skill_mcp_tools import SkillTools
from skill_application import freeze, revision
from tool_catalog import tools_for, validate_arguments

spec=importlib.util.spec_from_file_location('mcp_fixture_skill_store',Path(__file__).resolve().parents[1]/'skills/store.py')
packages=importlib.util.module_from_spec(spec);sys.modules[spec.name]=packages;spec.loader.exec_module(packages)

SERVER = r'''
import fs from 'node:fs';import readline from 'node:readline';import net from 'node:net';
const tools=JSON.parse(fs.readFileSync(new URL('./catalog.json',import.meta.url))).tools;let counter=0;
const send=v=>console.log(JSON.stringify({jsonrpc:'2.0',...v}));
for await(const line of readline.createInterface({input:process.stdin})){
 const q=JSON.parse(line),p=q.params??{};if(q.id===undefined)continue;
 if(q.method==='initialize')send({id:q.id,result:{protocolVersion:p.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'explicit-studio-test-fixture',version:'1'}}});
 else if(q.method==='tools/list')send({id:q.id,result:{tools}});
 else if(q.method==='tools/call'){
   if(p.arguments.delay_ms)await new Promise(r=>setTimeout(r,p.arguments.delay_ms));
   let result;if(p.name==='large')result={content:[{type:'text',text:'bound-evidence-'.repeat(10000)}]};
   else if(p.name==='image')result={content:[{type:'image',mimeType:'image/png',data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII='}]};
   else {const probe={};if(p.arguments.probe){
     for(const path of p.arguments.probe.read??[])try{probe[path]={text:fs.readFileSync(path,'utf8')}}catch(e){probe[path]={error:e.code}}
     for(const path of p.arguments.probe.write??[])try{fs.writeFileSync(path,'owned namespace probe');probe[path]={written:true}}catch(e){probe[path]={error:e.code}}
     probe.capabilities=fs.readFileSync('/proc/self/status','utf8').split('\n').filter(s=>/^(Cap|NoNewPrivs)/.test(s));
     if(p.arguments.probe.proxy_url)probe.webResponse=await new Promise((resolve,reject)=>{let value='';const s=net.connect({host:'127.0.0.1',port:3128});s.on('connect',()=>s.write('GET '+p.arguments.probe.proxy_url+' HTTP/1.1\r\nHost: own-public.example\r\nConnection: close\r\n\r\n'));s.on('data',b=>value+=b);s.on('end',()=>resolve(value));s.on('error',reject)});
     probe.hostConnection=await new Promise(resolve=>{const s=net.connect({host:'127.0.0.1',port:5010});s.setTimeout(250);s.once('connect',()=>{s.destroy();resolve('connected')});s.once('error',e=>resolve(e.code));s.once('timeout',()=>{s.destroy();resolve('timeout')})});
     const local=net.createServer(s=>s.end('private-loopback'));await new Promise(r=>local.listen(0,'127.0.0.1',r));
     probe.loopback=await new Promise((resolve,reject)=>{let value='';const s=net.connect({host:'127.0.0.1',port:local.address().port});s.on('data',b=>value+=b);s.on('end',()=>resolve(value));s.on('error',reject)});await new Promise(r=>local.close(r));
   }result={content:[{type:'text',text:JSON.stringify(p.arguments)}],structuredContent:{probe,nativeCounter:++counter,nativePid:process.pid,original:p.arguments,ambient:process.env.STUDIO_QA_SECRET??null,workspace:fs.readFileSync(process.cwd()+'/canary.txt','utf8')}};}
   send({id:q.id,result});
 }else send({id:q.id,result:{}});
}
'''


class ManagedBroker(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.projects=self.base/'Projects';self.projects.mkdir()
        self.skills=self.base/'Skills';self.db=packages.connect(self.skills)
        self.ident=str(uuid.uuid4());self.owner=str(uuid.uuid4());self.session=str(uuid.uuid4());self.run=str(uuid.uuid4())
        current=packages.create(self.db,self.skills,dict(id=self.ident,name='Managed fixture'))
        current=packages.sources.configure(self.db,self.skills,dict(id=self.ident,revision=current['skill']['revision'],
            source={'repository':'https://github.com/morluto/rea'},requestId=str(uuid.uuid4())),packages)
        source=dict(repository='https://github.com/morluto/rea',commit='a'*40,manifestHash='b'*64)
        root=packages.folder(self.skills/self.ident/'Runtimes'/source['commit']/('c'*64),True)
        packages.folder(root/'Node/bin',True)
        shutil.copyfile('/usr/bin/node',root/'Node/bin/node');os.chmod(root/'Node/bin/node',0o500)
        packages.atomic(root/'server.mjs',SERVER.encode())
        tools=[dict(name=n,inputSchema={'type':'object','properties':{'value':{'anyOf':[{'type':'null'},{'type':'string'}]}}}) for n in ('echo','large','image','studio_read_file')]
        catalog=dict(version=1,info={'version':'1'},tools=tools,prompts=[])
        packages.atomic(root/'catalog.json',encoded(catalog))
        files=[]
        for path in [root/'Node/bin/node',root/'server.mjs',root/'catalog.json']:
            raw=path.read_bytes();files.append(dict(path=path.relative_to(root).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),executable=bool(path.stat().st_mode&0o111)))
        def part(path):return next(dict(path=f['path'],sha256=f['sha256']) for f in files if f['path']==path)
        runtime=dict(schema=1,recipe='rea',version='1',source=source,node=part('Node/bin/node'),entry=dict(part('server.mjs'),arguments=['mcp']),catalog=part('catalog.json'),files=files,programs={})
        raw=encoded(runtime);packages.atomic(root/'runtime.json',raw)
        skill=root.parents[2]/'Workspace/SKILL.md'
        packages.atomic(skill,b'---\nname: managed-broker-fixture\ndescription: Exercise the explicit test broker.\n---\n\nUse only QA data.\n')
        tree=packages.inventory(skill.parent)[2]
        binding=dict(schema=1,repository=source['repository'],commit=source['commit'],sourceManifestHash=source['manifestHash'],
                     skillPath='.agents/skills/reverse-engineer-anything',recipe='rea',importedHash=tree,
                     runtime=dict(path=root.relative_to(self.skills/self.ident).as_posix(),manifestHash=hashlib.sha256(raw).hexdigest(),version='1'))
        current=packages.detail(self.db,self.skills,self.ident)
        packages.publish(self.db,self.skills,dict(id=self.ident,revision=current['skill']['revision'],draftHash=tree,requestId=str(uuid.uuid4())),'/usr/bin/node',publication=binding)
        workspace=self.projects/self.owner/'Workspace';workspace.mkdir(parents=True)
        (workspace/'canary.txt').write_text('selected project only')
        store=types.SimpleNamespace(projects=self.projects,workspace=workspace,owner_type='project',owner_id=self.owner,directory=self.projects/self.owner/'Sessions')
        permissions={'studio.'+name:True for name in tools_for()}
        self.worker=types.SimpleNamespace(store=store,config={'permissions':permissions},session_id=self.session,run_id=self.run,
            stopping=False,lease=object(),uncertain_effect=False,error=None,outcome='completed')
        self.worker.config['skillAccess']=freeze(store,{},mcp=True)
        self.entry=self.worker.config['skillAccess']['entries'][0]
        import skill_runtime
        self.broker=SkillTools(self.worker,starter=skill_runtime.local_start)
        self.worker.skill_mcp=self.broker

    async def asyncTearDown(self):
        await self.broker.close()
        self.db.close();self.temp.cleanup()

    async def test_frozen_schemas_native_arguments_receipts_and_disabled_selection(self):
        validate_arguments('skill_call',dict(skillId=self.ident,name='echo',argumentsJson='{"value":null}'))
        listed=await self.broker.call('skill_discover',{},'list')
        self.assertEqual(json.loads(listed['output'])['skills'][0]['tools'],4)
        schema=await self.broker.call('skill_discover',dict(skillId=self.ident,name='echo'),'schema')
        self.assertIn('anyOf',json.dumps(json.loads(schema['output'])['payload']))
        value=await self.broker.call('skill_call',dict(skillId=self.ident,name='echo',argumentsJson='{"value":null}'),'native-1')
        self.assertTrue(value['success'],value)
        payload=json.loads(value['output'])['payload']
        self.assertIsNone(payload['structuredContent']['original']['value'])
        self.assertIsNone(payload['structuredContent']['ambient'])
        self.assertEqual(payload['structuredContent']['workspace'],'selected project only')
        original=await self.broker.call('read_skill_result',dict(skillId=self.ident,reference=value['skillMcp']['reference']),'read')
        self.assertEqual(json.loads(original['output'])['payload'],payload)
        self.worker.config['skillAccess']['entries']=[]
        denied=await self.broker.call('read_skill_result',dict(skillId=self.ident,reference=value['skillMcp']['reference']),'disabled')
        self.assertFalse(denied['success'])

    async def test_native_name_collision_and_images_use_each_existing_engine_output(self):
        value=await self.broker.call('skill_call',dict(skillId=self.ident,name='studio_read_file',argumentsJson='{"value":"native skill method"}'),'collision')
        self.assertTrue(value['success'],value)
        self.assertEqual(json.loads(value['output'])['payload']['structuredContent']['original']['value'],'native skill method')
        image=await self.broker.call('skill_call',dict(skillId=self.ident,name='image',argumentsJson='{}'),'image')
        from development_tools import DevelopmentTools
        helper=types.SimpleNamespace(worker=self.worker,image_capable=lambda:True)
        codex=await DevelopmentTools.native_output(helper,image)
        self.assertEqual(codex['contentItems'][1]['type'],'inputImage')
        self.assertTrue(codex['contentItems'][1]['imageUrl'].startswith('data:image/png;base64,'))
        from claude_worker import ClaudeWorker
        self.worker.config['claudeModel']={'imageInput':'supported'}
        claude=await ClaudeWorker.mcp_output(self.worker,image)
        self.assertEqual(claude['content'][1]['type'],'image')
        self.assertEqual(claude['content'][1]['mimeType'],'image/png')
        self.worker.config['claudeModel']['imageInput']='unsupported'
        unsupported=await ClaudeWorker.mcp_output(self.worker,image)
        self.assertTrue(all(block['type']=='text' for block in unsupported['content']))
        self.assertIn('does not confirm visual inspection',unsupported['content'][1]['text'])

    async def test_complete_large_result_pages_and_session_boundary(self):
        value=await self.broker.call('skill_call',dict(skillId=self.ident,name='large',argumentsJson='{}'),'large')
        self.assertTrue(value['success'],value)
        ref=value['skillMcp']['reference'];page=json.loads(value['output']);pieces=[page['text']]
        while page['nextOffset'] is not None:
            value=await self.broker.call('read_skill_result',dict(skillId=self.ident,reference=ref,offset=page['nextOffset']),'page')
            page=json.loads(value['output']);pieces.append(page['text'])
        original=''.join(pieces).encode();self.assertEqual(len(json.loads(original)['content'][0]['text']),150000)
        self.assertEqual(hashlib.sha256(original).hexdigest(),page['sha256'])
        self.worker.session_id=str(uuid.uuid4())
        self.assertFalse((await self.broker.call('read_skill_result',dict(skillId=self.ident,reference=ref),'foreign'))['success'])

    async def test_file_permission_tampering_and_immutable_package_identity(self):
        self.worker.config['permissions']['studio.read_file']=False
        denied=await self.broker.call('skill_call',dict(skillId=self.ident,name='echo',argumentsJson='{}'),'permission')
        self.assertFalse(denied['success']);self.assertEqual(self.broker.clients,{})
        self.worker.config['permissions']['studio.read_file']=True
        runtime=self.skills/self.ident/self.entry['mcp']['sourceBinding']['runtime']['path']
        (runtime/'catalog.json').write_text('{}')
        denied=await self.broker.call('skill_call',dict(skillId=self.ident,name='echo',argumentsJson='{}'),'tampered')
        self.assertFalse(denied['success']);self.assertEqual(self.broker.clients,{})
        self.assertEqual(revision(self.projects,self.entry,verify_files=True)[2],self.entry['manifestHash'])
        self.assertEqual(freeze(self.worker.store,{self.ident:False},mcp=True)['entries'],[])


if __name__=='__main__':unittest.main()
