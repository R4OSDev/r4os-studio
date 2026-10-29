import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:net';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {createApp} from '../src/app.js';
await test('Statistics reads protect browser origin, session and exact owner scopes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'studio-stats-')),socket=join(root,'host.sock'),previous=process.env.STUDIO_AGENTS_SOCKET;
 process.env.STUDIO_AGENTS_SOCKET=socket;const calls:Record<string,unknown>[]=[];
 const server=createServer(client=>{let raw='';client.on('data',chunk=>{raw+=chunk;if(!raw.includes('\n'))return;const call=JSON.parse(raw);calls.push(call);client.end(JSON.stringify({result:{schema:1,tokens:{total:'18014398509481982'},coverage:{state:'partial'},...(call.scope==='session'?{totalGoalRuntime:{schema:1,durationMs:'90000',coverage:{state:'complete'}}}:{})}})+'\n');});});
 await new Promise<void>(resolve=>server.listen(socket,resolve));
 const app=createApp({projectDirectory:join(root,'Projects'),providers:{directory:join(root,'Providers')}});
 try{
  const id=randomUUID(),sid=randomUUID(),url=`/api/projects/${id}/sessions/${sid}/statistics`;
  assert.equal((await app.inject(url)).statusCode,403);
  assert.equal((await app.inject({url:'/api/statistics',headers:{origin:'http://foreign.test'}})).statusCode,403);
  const global=await app.inject('/api/statistics');assert.equal(global.statusCode,200);assert.equal(global.json().tokens.total,'18014398509481982');
  const auth=await app.inject('/api/projects'),headers={cookie:String(auth.headers['set-cookie']).split(';')[0]};
  const session=await app.inject({url,headers});assert.equal(session.statusCode,200);assert.equal(session.json().totalGoalRuntime.durationMs,'90000');assert.equal(global.json().totalGoalRuntime,undefined);
  assert.deepEqual(calls.at(-1),{operation:'statistics',scope:'session',ownerType:'project',ownerId:id,sessionId:sid});
  assert.equal((await app.inject({url:`/api/projects/${id}/statistics`,headers})).statusCode,200);
  const skillAuth=await app.inject('/api/skills'),skillHeaders={cookie:String(skillAuth.headers['set-cookie']).split(';')[0]};
  const skill=await app.inject({url:`/api/skills/${id}/sessions/${sid}/statistics`,headers:skillHeaders});assert.equal(skill.statusCode,200);assert.equal(skill.json().totalGoalRuntime.durationMs,'90000');assert.equal(calls.at(-1)?.ownerType,'skill');
  assert.equal((await app.inject({method:'POST',url:'/api/statistics',payload:{sql:'DROP'}})).statusCode,404);
 }finally{await app.close();await new Promise<void>(resolve=>server.close(()=>resolve()));if(previous===undefined)delete process.env.STUDIO_AGENTS_SOCKET;else process.env.STUDIO_AGENTS_SOCKET=previous;await rm(root,{recursive:true,force:true});}
});
