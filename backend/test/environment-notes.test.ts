import test from 'node:test';import assert from 'node:assert/strict';import {createServer} from 'node:net';import {mkdtemp,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';import {randomUUID} from 'node:crypto';import {createApp} from '../src/app.js';
await test('Environment note browser routes bind owner/session and protect user-only deletes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'studio-note-api-')),socket=join(root,'host.sock'),previous=process.env.STUDIO_AGENTS_SOCKET;process.env.STUDIO_AGENTS_SOCKET=socket;const calls:Record<string,unknown>[]=[];
 const server=createServer(client=>{let raw='';client.on('data',chunk=>{raw+=chunk;if(!raw.includes('\n'))return;calls.push(JSON.parse(raw));client.end(JSON.stringify({result:{revision:1,count:1,entries:[]}})+'\n');});});await new Promise<void>(resolve=>server.listen(socket,resolve));
 const app=createApp({projectDirectory:join(root,'Projects'),providers:{directory:join(root,'LLMProvider')}}),id=randomUUID(),sid=randomUUID(),note=randomUUID(),url=`/api/projects/${id}/sessions/${sid}/environment-notes`;
 try{
  assert.equal((await app.inject(url)).statusCode,403);const auth=await app.inject('/api/projects'),headers={cookie:String(auth.headers['set-cookie']).split(';')[0],'x-csrf-token':auth.json().csrfToken};
  assert.equal((await app.inject({url,headers})).statusCode,200);assert.deepEqual(calls.at(-1),{operation:'environment_notes',ownerType:'project',ownerId:id,sessionId:sid,query:{}});
  const payload={requestId:randomUUID(),collectionRevision:1,revision:1};assert.equal((await app.inject({method:'DELETE',url:url+'/'+note,payload,headers:{cookie:headers.cookie}})).statusCode,403);
  assert.equal((await app.inject({method:'DELETE',url:url+'/'+note,payload,headers:{...headers,origin:'http://foreign.test'}})).statusCode,403);
  assert.equal((await app.inject({method:'DELETE',url:url+'/'+note,payload,headers})).statusCode,200);assert.equal(calls.at(-1)?.noteId,note);
  assert.equal((await app.inject({method:'POST',url,payload:{title:'Browser cannot create agent notes'},headers})).statusCode,404);
  assert.equal((await app.inject({method:'POST',url:url+'/delete-all',payload:{requestId:randomUUID(),collectionRevision:1,confirmName:'Owned session',count:1},headers})).statusCode,200);
 }finally{await app.close();await new Promise<void>(resolve=>server.close(()=>resolve()));if(previous===undefined)delete process.env.STUDIO_AGENTS_SOCKET;else process.env.STUDIO_AGENTS_SOCKET=previous;await rm(root,{recursive:true,force:true});}
});
