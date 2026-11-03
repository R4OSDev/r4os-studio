import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chatRequest, ChatStream, ChatFault } from './api_chat.mjs';
import { ReasoningStore } from './api_reasoning_store.mjs';
import { routerRequest, routerSettings } from './api_openrouter.mjs';

const facts={mandatory:true,supported_efforts:['max','minimal'],default_effort:'max'};
const policy={schema:2,systemRole:'system',reasoning:'effort',reasoningFacts:facts,efforts:['max','minimal'],selectedEffort:'max',functionTools:true,streaming:true};
const base=()=>({model:'owned/reasoner',input:[{type:'message',role:'user',content:'Owned request'}],tools:[{type:'function',name:'studio_owned',parameters:{type:'object'}}],
  tool_choice:'auto',parallel_tool_calls:true,reasoning:{effort:'max'},stream:true,store:false});
function fixture(t) {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'studio-reasoning-'));fs.chmodSync(directory,0o700);
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const config={directory,scope:{ownerType:'project',ownerId:'owner',sessionId:'session',providerId:'provider',model:'owned/reasoner',baseUrl:'https://example.test/v1',protocol:'chat-completions'},origin:{configRevision:1}};
  return {config,store:new ReasoningStore(config)};
}
const frame=(delta,finish_reason=null)=>Buffer.from('data: '+JSON.stringify({id:'owned-provider-id',choices:[{index:0,delta,finish_reason}]})+'\n\n');
function response(store,variant='tools') {
  const request=base(),events=[],wire=chatRequest(request,policy,store);
  const parser=new ChatStream(wire,event=>events.push(event),{reasoning:(...args)=>store.capture(...args)});
  parser.push(frame({reasoning_content:'raw ',reasoning_details:[
    {type:'reasoning.text',text:'Original 🧠 ',signature:null,id:'text-1',format:'openrouter-stealth-v1',index:0},
    {type:'reasoning.encrypted',data:'opaque-',id:'encrypted-1',format:'openrouter-stealth-v1',index:1}]}));
  parser.push(frame({reasoning_content:'original',reasoning_details:[
    {type:'reasoning.text',text:'reasoning',signature:'signed-original',index:0},
    {type:'reasoning.encrypted',data:'original',index:1},
    {type:'reasoning.summary',summary:'Original summary',id:null,format:'unknown',index:2}]}));
  if(variant==='tools')parser.push(frame({tool_calls:[{index:0,id:'original-call',type:'function',function:{name:'studio_owned',arguments:'{"owned":true}'}}]},'tool_calls'));
  else parser.push(frame({},'length'));
  return {request,events,parser};
}
test('reasoning roundtrip survives restart with exact blocks and tool IDs',t=>{
  const {store,config}=fixture(t),{request,events,parser}=response(store);
  assert.equal(events.filter(v=>v.type==='response.output_item.done').length,0);
  parser.push(Buffer.from('data: [DONE]\n\n'));parser.push(new Uint8Array(),true);
  const items=events.filter(v=>v.type==='response.output_item.done').map(v=>v.item);
  assert.deepEqual(items.map(v=>v.type),['reasoning','function_call']);assert.equal(JSON.stringify(events).includes('signed-original'),false);
  const next={...request,input:[...request.input,...items,{type:'function_call_output',call_id:'original-call',output:'Original acknowledged result'}]};
  const resumed=new ReasoningStore({...config,origin:{configRevision:2}}),wire=routerRequest(chatRequest(next,policy,resumed),routerSettings(),policy);
  const assistant=wire.messages.find(v=>v.role==='assistant');
  assert.deepEqual(assistant.reasoning_details,[{type:'reasoning.text',id:'text-1',format:'openrouter-stealth-v1',index:0,text:'Original 🧠 reasoning',signature:'signed-original'},
    {type:'reasoning.encrypted',id:'encrypted-1',format:'openrouter-stealth-v1',index:1,data:'opaque-original'},
    {type:'reasoning.summary',id:null,format:'unknown',index:2,summary:'Original summary'}]);
  assert.equal(assistant.reasoning_content,'raw original');assert.equal(assistant.tool_calls[0].id,'original-call');
  assert.deepEqual(wire.reasoning,{effort:'max'});assert.equal(wire.reasoning_effort,undefined);
  const wrong=structuredClone(next);wrong.input[1].encrypted_content=wrong.input[1].encrypted_content.replace(/.$/,'z');
  assert.throws(()=>chatRequest(wrong,policy,resumed),ChatFault);
  const missing=structuredClone(next);missing.input.splice(1,1);assert.throws(()=>chatRequest(missing,policy,resumed),ChatFault);
  const changed=structuredClone(next);changed.input[2].arguments='{}';assert.throws(()=>chatRequest(changed,policy,resumed),ChatFault);
  const foreign=new ReasoningStore({...config,scope:{...config.scope,sessionId:'foreign'}});
  assert.throws(()=>chatRequest(next,policy,foreign),ChatFault);
});
test('mandatory and implicit defaults remain distinct from explicit none',t=>{
  const {store}=fixture(t),native=base();native.reasoning={effort:'medium'};
  const implicit={...policy,efforts:[''],selectedEffort:'',reasoningFacts:{mandatory:true}};
  const wire=routerRequest(chatRequest(native,implicit,store),routerSettings(),implicit);
  assert.equal(wire.reasoning,undefined);assert.equal(wire.reasoning_effort,undefined);
  assert.throws(()=>chatRequest({...native,reasoning:{effort:'none'}},{...policy,efforts:['none'],selectedEffort:'none'},store),ChatFault);
});
test('limits, partial streams and length never release tool prefixes or invent output',t=>{
  const {store,config}=fixture(t),incomplete=response(store,'length');
  incomplete.parser.push(Buffer.from('data: [DONE]\n\n'));assert.equal(incomplete.events.at(-1).type,'response.incomplete');
  assert.equal(incomplete.events.some(v=>v.type==='response.output_text.delta'||v.type==='response.output_item.done'),false);
  const lost=response(store);assert.throws(()=>lost.parser.push(new Uint8Array(),true),ChatFault);
  assert.equal(lost.events.some(v=>v.type==='response.output_item.done'),false);
  const parser=new ChatStream(chatRequest(base(),policy,store),()=>{}, {reasoning:(...args)=>store.capture(...args)});
  assert.throws(()=>parser.push(frame({reasoning:'x'.repeat(5*1024*1024)})),ChatFault);
  fs.symlinkSync('/dev/null',path.join(config.directory,'link.json'));assert.throws(()=>new ReasoningStore(config),ChatFault);
});
