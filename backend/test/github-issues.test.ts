import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {GitHubIssues,ISSUES_QUERY} from '../src/modules/project-github/issues.js';
import {GitHubStore} from '../src/modules/github-connections/store.js';
import type {GitHubProjectBinding} from '../../shared/project-github.js';
import {createApp} from '../src/app.js';

const issue=(number:number,state='OPEN')=>({__typename:'Issue',number,title:'Literal <img onerror="bad()"> title '+number,state,url:'https://github.com/own/app/issues/'+number,updatedAt:'2026-10-30T07:00:00Z',labels:{nodes:[{name:'enhancement',color:'a879c4'}],totalCount:1}});
const result=(nodes=[issue(1)],next:string|null=null,count=51)=>({data:{viewer:{databaseId:7},repository:{databaseId:11,nameWithOwner:'own/app',hasIssuesEnabled:true,openIssues:{totalCount:count},issuePage:{nodes,pageInfo:{hasNextPage:next!==null,endCursor:next}}}}});
async function setup(){
  const root=await mkdtemp(join(tmpdir(),'studio-issues-')),store=new GitHubStore(join(root,'GitHub')),connectionId=randomUUID(),id=randomUUID();
  await store.create({id:connectionId,name:'Owned',token:'owned-dummy-token-1234567890'});
  const binding:GitHubProjectBinding={schema:1,revision:1,connectionId,userId:7,repository:{id:11,owner:'own',name:'app',fullName:'own/app',url:'https://github.com/own/app',private:true,archived:false,defaultBranch:'main',read:true,push:false},branch:'main',author:{name:'Own',email:'own@example.invalid'}};
  return{root,store,connectionId,id,binding};
}

await test('fixed issue query shares bounded reads, counts all open issues independently of cursor/filter and distinguishes zero',async()=>{
  const f=await setup();let calls=0,zero=false;
  try{
    const reader=new GitHubIssues(f.store,async()=>f.binding,async(url,init)=>{
      assert.equal(String(url),'https://api.github.com/graphql');assert.equal(init?.method,'POST');assert.equal(init?.redirect,'manual');
      const body=JSON.parse(String(init?.body));assert.equal(body.query,ISSUES_QUERY);assert(!body.query.includes('mutation'));
      assert.deepEqual([body.variables.owner,body.variables.name],['own','app']);calls++;
      await new Promise(r=>setTimeout(r,20));
      return new Response(JSON.stringify(zero?result([],null,0):result([issue(body.variables.after?2:1,body.variables.states?.[0]??'OPEN')],body.variables.after?null:'native-next')));
    });
    const [first,joined]=await Promise.all([reader.read(f.id,1,'open',null),reader.read(f.id,1,'open',null)]);
    assert.equal(calls,1);assert.deepEqual(first,joined);assert.equal(first.openCount,51);assert.equal(first.items.length,1);assert(first.nextCursor);
    assert.equal((await reader.read(f.id,1,'open',null)).cached,true);assert.equal(calls,1);
    const next=await reader.read(f.id,1,'open',first.nextCursor);assert.equal(next.items[0].number,2);assert.equal(next.openCount,51);
    const closed=await reader.read(f.id,1,'closed',null);assert.equal(closed.items[0].state,'closed');assert.equal(closed.openCount,51);
    await assert.rejects(reader.read(f.id,1,'closed',first.nextCursor),/expired|earlier/);
    const before=calls;await assert.rejects(reader.read(f.id,1,'open',first.nextCursor+'x'),/expired|earlier/);assert.equal(calls,before);
    zero=true;const empty=await reader.read(f.id,1,'open',null,true);assert.equal(empty.openCount,0);assert.deepEqual(empty.items,[]);
    assert(!JSON.stringify(first).includes('owned-dummy-token'));
  }finally{await rm(f.root,{recursive:true,force:true});}
});

await test('partial GraphQL, PR/unsafe data, denied/rate-limited and changed identities never become an issue count',async()=>{
  const f=await setup();let value:unknown=result();
  const reader=new GitHubIssues(f.store,async()=>f.binding,async()=>new Response(JSON.stringify(value)));
  try{
    for(const [raw,pattern] of [
      [{...result(),errors:[{type:'FORBIDDEN',message:'PRIVATE UPSTREAM ERROR'}]},/denied issue access/],
      [{...result(),errors:[{type:'RATE_LIMITED'}]},/rate limit/],
      [{data:result().data,errors:[{type:'INTERNAL'}]},/incomplete issue query/],
      [result([{...issue(1),__typename:'PullRequest'}]),/invalid issue data/],
      [result([{...issue(1),url:'javascript:bad()'}]),/invalid issue data/]
    ] as const){value=raw;await assert.rejects(reader.read(f.id,1,'open',null,true),(e:Error)=>pattern.test(e.message)&&!e.message.includes('PRIVATE'));}
    value={data:{...result().data,viewer:{databaseId:8}}};await assert.rejects(reader.read(f.id,1,'open',null,true),/account/);
    value={data:{...result().data,repository:{...result().data.repository,databaseId:12}}};await assert.rejects(reader.read(f.id,1,'open',null,true),/identity changed/);
    value={data:{...result().data,repository:{...result().data.repository,hasIssuesEnabled:false}}};await assert.rejects(reader.read(f.id,1,'open',null,true),/disabled/);
  }finally{await rm(f.root,{recursive:true,force:true});}
});

await test('binding/token replacement during a shared issue request cannot publish or reuse its old data',async()=>{
  const f=await setup();let tokenChange=false;
  const reader=new GitHubIssues(f.store,async()=>f.binding,async()=>{
    if(tokenChange)await f.store.update(f.connectionId,{revision:1,name:'Owned',token:'new-owned-dummy-token-1234567890'});
    else f.binding={...f.binding,revision:2,branch:'other'};
    return new Response(JSON.stringify(result()));
  });
  try{
    await assert.rejects(reader.read(f.id,1,'open',null),/connection changed/);
    f.binding={...f.binding,revision:1,branch:'main'};tokenChange=true;
    await assert.rejects(reader.read(f.id,1,'open',null,true),/token changed/);
  }finally{await rm(f.root,{recursive:true,force:true});}
});

await test('a late successful response cannot restore cached issues after a concurrent access denial',async()=>{
  const f=await setup();let release!:()=>void,started!:()=>void;
  const waiting=new Promise<void>(resolve=>{release=resolve;}),ready=new Promise<void>(resolve=>{started=resolve;});
  const reader=new GitHubIssues(f.store,async()=>f.binding,async(_url,init)=>{
    const body=JSON.parse(String(init?.body));
    if(body.variables.states[0]==='CLOSED')return new Response(JSON.stringify({...result(),errors:[{type:'FORBIDDEN'}]}));
    started();await waiting;return new Response(JSON.stringify(result()));
  });
  try{
    const old=reader.read(f.id,1,'open',null);await ready;
    await assert.rejects(reader.read(f.id,1,'closed',null),/denied issue access/);
    release();await assert.rejects(old,/access changed/);
  }finally{release();await rm(f.root,{recursive:true,force:true});}
});

await test('project issue HTTP read keeps session/origin/query gates and returns only its confirmed bound repository',async()=>{
  const f=await setup(),projects=join(f.root,'Projects'),providers=join(f.root,'LLMProvider');
  const app=createApp({projectDirectory:projects,providers:{directory:providers},githubTransport:async()=>new Response(JSON.stringify(result()))});
  try{
    const root=await app.inject('/api/projects'),headers={cookie:String(root.headers['set-cookie']).split(';')[0]};
    const program="import sys;sys.path.insert(0,sys.argv[1]);from store import connect;db=connect(__import__('pathlib').Path(sys.argv[2]));db.execute(\"INSERT INTO projects VALUES (?,?,'','C','terminal','OWN',NULL,'{}','now','now',1,'ready')\",(sys.argv[3],'Own'));db.commit();db.close()";
    const seed=spawnSync('/usr/bin/python3',['-B','-c',program,fileURLToPath(new URL('../../scripts/projects/',import.meta.url)),projects,f.id],{encoding:'utf8'});assert.equal(seed.status,0,seed.stderr);
    const privateRoot=join(projects,f.id,'.studio/git');await mkdir(privateRoot,{recursive:true});await writeFile(join(privateRoot,'binding.json'),JSON.stringify(f.binding));
    const path=`/api/projects/${f.id}/github/issues?bindingRevision=1`;
    assert.equal((await app.inject(path)).statusCode,403);
    assert.equal((await app.inject({url:path,headers:{...headers,origin:'http://foreign.invalid'}})).statusCode,403);
    assert.equal((await app.inject({url:path+'&query=mutation',headers})).statusCode,400);
    const read=await app.inject({url:path,headers});assert.equal(read.statusCode,200,read.body);assert.equal(read.json().openCount,51);assert.equal(read.json().scope.projectId,f.id);
    assert.equal(read.headers['cache-control'],'private, no-store');assert(!read.body.includes('owned-dummy-token'));
    assert.equal((await app.inject({url:path.replace(f.id,randomUUID()),headers})).statusCode,404);
  }finally{await app.close();await rm(f.root,{recursive:true,force:true});}
});
