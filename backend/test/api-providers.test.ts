import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('API connection CRUD is protected, bounded and masks credentials independently of subscriptions', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-api-providers-')), socket = join(root, 'host.sock');
  const previous = process.env.STUDIO_AGENTS_SOCKET; process.env.STUDIO_AGENTS_SOCKET = socket;
  const id = randomUUID(), requestId = randomUUID(), secret = 'fixture-only-bearer-key', calls: Record<string, unknown>[] = [];
  let available = true;
  const provider = { id, type: 'api', kind: 'openai-compatible', name: 'Own fixture', baseUrl: 'https://models.example.test/v1',
    protocol: 'responses', auth: 'bearer', revision: 1, credentialRevision: 1, keyConfigured: true, enabled: true,
    status: 'configured', createdAt: 'now', updatedAt: 'now', runtime: 'not-qualified' };
  const server = createServer(client => {
    let raw = ''; client.on('data', chunk => {
      raw += chunk; if (!raw.includes('\n')) return;
      const call = JSON.parse(raw); calls.push(call);
      const result = call.action === 'list' ? [provider] : call.action === 'get' ? provider : { requestId, state: 'complete', provider };
      client.end(JSON.stringify(available ? { result } : { error: 'API provider support is unavailable.', code: 503 }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  const base = '/api/providers/api-connections';
  try {
    assert.equal((await app.inject(base)).statusCode,403); assert.equal(calls.length,0);
    const auth = await app.inject('/api/providers/'); assert.equal(auth.statusCode,200,auth.body);
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const body = { requestId, name: provider.name, kind: provider.kind, baseUrl: provider.baseUrl, protocol: provider.protocol, auth: provider.auth, key: secret };
    for (const extra of [{origin:'http://foreign.invalid'},{origin:'https://localhost'},{host:'foreign.invalid'},{'sec-fetch-site':'cross-site'}]) {
      assert.equal((await app.inject({url:base,headers:{...headers,...extra}})).statusCode,403);
    }
    assert.equal((await app.inject({method:'POST',url:base,headers:{cookie:headers.cookie},payload:body})).statusCode,403);
    const created = await app.inject({method:'POST',url:base,headers,payload:body});
    assert.equal(created.statusCode,201,created.body); assert.equal(created.json().provider.keyConfigured,true); assert.ok(!created.body.includes(secret));
    assert.deepEqual(calls.at(-1),{operation:'api_provider',action:'create',input:body});
    assert.equal((await app.inject({url:base,headers})).json().providers[0].id,id);
    assert.equal((await app.inject({url:base+'/'+id,headers})).json().provider.id,id);
    for(const payload of [{...body,unexpected:true},{...body,key:4},{...body,key:'a'.repeat(20000)}]) {
      const result = await app.inject({method:'POST',url:base,headers,payload});
      assert.ok([400,413].includes(result.statusCode),result.body);
    }
    const patch = {requestId,revision:1,key:null};
    assert.equal((await app.inject({method:'PATCH',url:base+'/'+id,headers,payload:patch})).statusCode,200);
    assert.deepEqual(calls.at(-1),{operation:'api_provider',action:'update',id,input:patch});
    for(const [method,url,action] of [['POST',base+'/'+id+'/disconnect','disconnect'],['DELETE',base+'/'+id,'delete']]) {
      assert.equal((await app.inject({method:method as 'POST'|'DELETE',url,headers,payload:{requestId,revision:1}})).statusCode,200);
      assert.equal(calls.at(-1)?.action,action);
    }
    const receipt = await app.inject({url:base+'/'+id+'/requests/'+requestId,headers});
    assert.equal(receipt.json().state,'complete');assert.equal(calls.at(-1)?.action,'receipt');assert.ok(!receipt.body.includes(secret));
    assert.equal((await app.inject({url:base+'/creation-requests/'+requestId,headers})).statusCode,200);
    assert.equal(calls.at(-1)?.action,'creation_receipt');
    assert.equal((await app.inject({url:base+'/'+id+'/models',headers})).statusCode,200);
    assert.equal(calls.at(-1)?.action,'models');
    const check={requestId,providerRevision:1};
    assert.equal((await app.inject({method:'POST',url:base+'/'+id+'/models/check',headers:{cookie:headers.cookie},payload:check})).statusCode,403);
    assert.equal((await app.inject({method:'POST',url:base+'/'+id+'/models/check',headers,payload:check})).statusCode,200);
    assert.equal(calls.at(-1)?.action,'catalog_refresh');
    const model={id:'own/exact',name:'Own model',contextWindow:8192,maxOutputTokens:null,
      capabilities:Object.fromEntries(['text','functionTools','streaming','imageInput','reasoning','webSearch','imageGeneration','goals'].map(key=>[key,'unknown'])),efforts:[],defaultEffort:null};
    const manual={requestId,providerRevision:1,catalogRevision:0,model};
    assert.equal((await app.inject({method:'POST',url:base+'/'+id+'/models',headers,payload:manual})).statusCode,200);
    assert.equal(calls.at(-1)?.action,'model_save');
    const beforeInvalid=calls.length;
    for(const [path,payload] of [['/models/check',{...check,providerRevision:'1'}],['/models',{...manual,catalogRevision:'0'}],
      ['/models',{...manual,model:{...model,contextWindow:'8192'}}],['/models',{...manual,model:{...model,capabilities:{...model.capabilities,text:true}}}],
      ['/models',{...manual,model:{...model,unexpected:secret}}]]) {
      assert.equal((await app.inject({method:'POST',url:base+'/'+id+path,headers,payload})).statusCode,400);
    }
    assert.equal(calls.length,beforeInvalid);
    assert.equal((await app.inject({url:base+'/'+id+'/model-requests/'+requestId,headers})).statusCode,200);
    assert.equal(calls.at(-1)?.action,'catalog_receipt');
    assert.ok(calls.every(call=>call.operation==='api_provider'));
    available=false;assert.equal((await app.inject({url:base,headers})).statusCode,503);
    assert.equal((await app.inject({url:'/api/providers/',headers})).statusCode,200);
  } finally {
    await app.close();await new Promise<void>(resolve => server.close(() => resolve()));
    if(previous===undefined)delete process.env.STUDIO_AGENTS_SOCKET;else process.env.STUDIO_AGENTS_SOCKET=previous;
    await rm(root,{recursive:true,force:true});
  }
});
