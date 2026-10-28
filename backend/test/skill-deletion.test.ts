import test from 'node:test';import assert from 'node:assert/strict';import {createServer} from 'node:net';import {mkdtemp,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';import {randomUUID} from 'node:crypto';import {createApp} from '../src/app.js';
await test('Complete skill deletion protects CSRF and retains an original receipt after disappearance',async()=>{
 const root=await mkdtemp(join(tmpdir(),'studio-delete-skill-')),socket=join(root,'host.sock'),previous=process.env.STUDIO_AGENTS_SOCKET;process.env.STUDIO_AGENTS_SOCKET=socket;
 const calls:Record<string,unknown>[]=[],id=randomUUID(),rid=randomUUID();
 const server=createServer(client=>{let raw='';client.on('data',chunk=>{raw+=chunk;if(!raw.includes('\n'))return;const call=JSON.parse(raw);calls.push(call);client.end(JSON.stringify({result:call.operation==='capabilities'?{skillDeletion:1}:{id,requestId:rid,state:call.operation==='skill_delete_receipt'?'deleted':'deleting',phase:'reserved'}})+'\n');});});
 await new Promise<void>(resolve=>server.listen(socket,resolve));const app=createApp({projectDirectory:join(root,'Projects'),providers:{directory:join(root,'LLMProvider')}});
 try{
  const base=`/api/skills/${id}/deletion`,payload={requestId:rid,revision:1,scopeHash:'a'.repeat(64),confirmName:'Own synthetic skill'};
  assert.equal((await app.inject({url:base})).statusCode,403);assert.equal((await app.inject({method:'POST',url:base,payload})).statusCode,403);
  const auth=await app.inject('/api/skills');assert.equal(auth.statusCode,200);const headers={cookie:String(auth.headers['set-cookie']).split(';')[0],'x-csrf-token':auth.json().csrfToken};
  assert.equal((await app.inject({method:'POST',url:base,payload,headers:{...headers,origin:'http://foreign.test'}})).statusCode,403);
  assert.equal((await app.inject({method:'POST',url:base,payload,headers})).statusCode,202);assert.deepEqual(calls.at(-1),{operation:'skill_delete',ownerId:id,input:payload});
  const receipt=await app.inject({url:base+'/'+rid,headers});assert.equal(receipt.statusCode,200);assert.equal(receipt.json().state,'deleted');
  assert.equal((await app.inject({method:'POST',url:base,payload:{...payload,scopeHash:'bad'},headers})).statusCode,400);
 }finally{await app.close();await new Promise<void>(resolve=>server.close(()=>resolve()));if(previous===undefined)delete process.env.STUDIO_AGENTS_SOCKET;else process.env.STUDIO_AGENTS_SOCKET=previous;await rm(root,{recursive:true,force:true});}
});
