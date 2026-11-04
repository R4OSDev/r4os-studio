/** Sign in with ChatGPT public client. Account operations only; never an agent. */
import { createServer } from 'node:http';
import { createHash, randomBytes, randomUUID, timingSafeEqual, createPublicKey, verify } from 'node:crypto';
import { constants } from 'node:fs';
import { open, lstat, realpath, rename, mkdir, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { createInterface } from 'node:readline';
const issuer='https://auth.openai.com', resource='https://api.openai.com/v1';
const required=['openid','profile','email','offline_access','resource.invoke','chatgpt.tokens.use.direct'];
const planPermission=value=>['resource.invoke','chatgpt.tokens.use.direct'].every(s=>value.scopes.includes(s));
const scopes=value=>typeof value==='string'?value.split(/\s+/).filter(Boolean):[];
const equal=(a,b)=>{if(typeof a!=='string'||typeof b!=='string')return false;const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);};
const text=(v,max=8192)=>typeof v==='string'&&v.length>0&&v.length<=max&&![...v].some(c=>c.codePointAt(0)<=32||c.codePointAt(0)===127);
async function privateFile(path) {
 const p=resolve(path),s=await lstat(p);
 if(await realpath(p)!==p||!s.isFile()||s.nlink!==1||(s.mode&0o777)!==0o600||process.getuid&&s.uid!==process.getuid())throw Error('private_file_unavailable');
 if(s.size>131072)throw Error('private_file_limit');return JSON.parse(await readFile(p,'utf8'));
}
async function atomic(path,value) {
 const p=resolve(path),parent=dirname(p);await mkdir(parent,{recursive:true,mode:0o700});
 if(await realpath(parent)!==parent)throw Error('private_path_unavailable');
 const part=p+'.'+randomUUID()+'.pending',fd=await open(part,constants.O_CREAT|constants.O_EXCL|constants.O_WRONLY|constants.O_NOFOLLOW,0o600);
 try{await fd.writeFile(JSON.stringify(value));await fd.sync();}finally{await fd.close();}await rename(part,p);
}
async function http(url,form) {
 if(!url.startsWith(issuer+'/'))throw Error('unexpected_auth_endpoint');
 const response=await fetch(url,{method:form?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(20000),
  headers:{Accept:'application/json',...(form?{'Content-Type':'application/x-www-form-urlencoded'}:{})},...(form?{body:new URLSearchParams(form)}:{})});
 let bytes=0,parts=[];for await(const part of response.body){bytes+=part.length;if(bytes>1048576)throw Error('auth_response_limit');parts.push(part);}
 const body=Buffer.concat(parts),raw=body.toString('utf8');
 if(!response.ok){const error=Error('auth_http_'+response.status);error.originalError={httpStatus:response.status,bodyBase64:body.subarray(0,65536).toString('base64'),bodySha256:createHash('sha256').update(body).digest('hex'),bodyTruncated:body.length>65536};throw error;}
 return raw?JSON.parse(raw):{};
}
async function discovery() {
 const value=await http(issuer+'/.well-known/openid-configuration');
 if(value.issuer!==issuer||value.token_endpoint!==issuer+'/api/accounts/oauth/token'||value.jwks_uri!==issuer+'/.well-known/jwks.json'
  ||value.revocation_endpoint!==issuer+'/api/accounts/oauth/revoke')throw Error('auth_discovery_changed');
 return value;
}
async function identity(token,client,nonce,allowExpired=false) {
 if(!text(token,32768)||!text(client,256)||client==='dynamic_agent_client')throw Error('registration_incomplete');
 const parts=token.split('.');if(parts.length!==3)throw Error('invalid_id_token');
 const header=JSON.parse(Buffer.from(parts[0],'base64url')),payload=JSON.parse(Buffer.from(parts[1],'base64url'));
 if(header.alg!=='RS256'||!text(header.kid,256))throw Error('invalid_id_signature');
 const jwks=await http((await discovery()).jwks_uri);
 const keys=jwks.keys?.filter(k=>k.kid===header.kid&&k.kty==='RSA'&&(!k.alg||k.alg==='RS256')&&(!k.use||k.use==='sig'));
 if(keys?.length!==1||!verify('RSA-SHA256',Buffer.from(parts[0]+'.'+parts[1]),createPublicKey({key:keys[0],format:'jwk'}),Buffer.from(parts[2],'base64url')))throw Error('invalid_id_signature');
 const audience=Array.isArray(payload.aud)?payload.aud:[payload.aud],now=Date.now()/1000;
 if(payload.iss!==issuer||!audience.includes(client)||audience.length>1&&payload.azp!==client||!text(payload.sub,256)
  ||!Number.isSafeInteger(payload.exp)||!allowExpired&&payload.exp<=now||payload.iat!=null&&(!Number.isSafeInteger(payload.iat)||payload.iat>now+60)
  ||nonce!==undefined&&!equal(payload.nonce,nonce))throw Error('invalid_id_identity');
 return {issuer,subject:payload.sub,...(typeof payload.email==='string'&&payload.email.length<=320?{email:payload.email}:{})};
}
async function tokenSet(value,client,host,expected,nonce,retainScopes=false) {
 if(!text(value.access_token)||!text(value.refresh_token)||value.token_type?.toLowerCase()!=='bearer'
  ||!Number.isSafeInteger(value.expires_in)||value.expires_in<=0||value.expires_in>86400)throw Error('invalid_token_response');
 const id=await identity(value.id_token??expected?.id_token,client,nonce,value.id_token===undefined);
 if(expected&&(expected.client_id!==client||expected.issuer!==id.issuer||expected.subject!==id.subject))throw Error('account_identity_changed');
 return {schema:1,kind:'studio-siwc',...id,client_id:client,ext_agent_host_id:host,id_token:value.id_token??expected.id_token,
  access_token:value.access_token,refresh_token:value.refresh_token,token_type:'Bearer',scopes:scopes(value.scope??(retainScopes?expected.scopes.join(' '):'')),
  expires_at:new Date(Date.now()+value.expires_in*1000).toISOString(),saved_at:new Date().toISOString()};
}
async function main(config, input) {
 const {mode,path,statusPath,hostId}=config;
 const status=async value=>{if(!statusPath)return;let previous={};try{previous=await privateFile(statusPath);}catch(error){if(error.code!=='ENOENT')throw error;}await atomic(statusPath,{...previous,...value,updatedAt:new Date().toISOString()});};
 if(!text(hostId,256)||!['signin','refresh','validate','revoke'].includes(mode)||typeof path!=='string')throw Error('invalid_auth_operation');
 if(mode!=='signin') {
  const original=await privateFile(path);
  if(original.kind!=='studio-siwc'||original.schema!==1||!text(original.client_id,256)||original.client_id==='dynamic_agent_client')throw Error('registration_incomplete');
  await identity(original.id_token,original.client_id,undefined,true);
  if(mode==='validate'){await status({state:'validated'});return;}
  const metadata=await discovery();await status({state:'sent',operation:mode,issuedClientId:original.client_id});
  if(mode==='revoke') {
   await http(metadata.revocation_endpoint,{client_id:original.client_id,token:original.refresh_token,token_type_hint:'refresh_token'});
   await status({state:'revoked'});return;
  }
  // No retry: a lost rotating-refresh response requires explicit reauthorization.
  const response=await http(metadata.token_endpoint,{grant_type:'refresh_token',client_id:original.client_id,refresh_token:original.refresh_token,resource});
  const value=await tokenSet({...response,refresh_token:response.refresh_token??original.refresh_token},original.client_id,hostId,original,undefined,config.requireGrantedScope!==true);
  await atomic(path,value);await status({state:planPermission(value)?'authorized':'permissionMissing',authorizationConfirmed:true,planPermission:planPermission(value)});return;
 }
 const original=config.registrationPath?await privateFile(config.registrationPath):null;
 if(original){if(original.kind!=='studio-siwc'||original.schema!==1)throw Error('registration_incomplete');await identity(original.id_token,original.client_id,undefined,true);}
 const client=original?.client_id??config.issuedClientId??'dynamic_agent_client',state=randomBytes(32).toString('base64url'),nonce=randomBytes(32).toString('base64url'),verifier=randomBytes(48).toString('base64url');
 let consumed=false,finished=false,timer,finish;
 const completed=new Promise(resolve=>{finish=resolve;});
 const receive=async(value,answer)=>{
  let url;
  try{url=new URL(value);}catch{answer(400,'Invalid callback.');return;}
  if(value.length>16384||url.origin+url.pathname!==callback||url.username||url.password||url.hash
   ||!equal(url.searchParams.get('state'),state)||[...url.searchParams.keys()].some(k=>url.searchParams.getAll(k).length!==1
    ||!['code','state','client_id','scope','error','error_description','error_uri'].includes(k))) {answer(400,'This callback does not match the original login.');return;}
  if(consumed||finished){answer(409,'This original callback is already handled.');return;}
  consumed=true;clearTimeout(timer);
  try {
   if(url.searchParams.has('error')){await status({state:'denied'});answer(400,'Sign-in was declined. Return to Studio.');return;}
   const issued=url.searchParams.get('client_id')??(client!=='dynamic_agent_client'?client:null),code=url.searchParams.get('code');
   if(!text(issued,256)||issued==='dynamic_agent_client'||client!=='dynamic_agent_client'&&issued!==client||!text(code,16384))throw Error('registration_incomplete');
   await status({state:'exchanging',issuedClientId:issued});
   const tokens=await http((await discovery()).token_endpoint,{grant_type:'authorization_code',client_id:issued,code,code_verifier:verifier,redirect_uri:callback,resource});
   const value=await tokenSet(tokens,issued,hostId,original??config.expectedIdentity,nonce);await atomic(path,value);
   await status({state:planPermission(value)?'authorized':'permissionMissing',authorizationConfirmed:true,planPermission:planPermission(value)});
   answer(200,'Sign-in received. Return to R4OS Studio. No model request was made.');
  }catch(error) {await status({state:error.originalError?'failed':'unknown',...(error.originalError?{originalError:error.originalError}:{}),error:'The original sign-in could not be confirmed. Do not resend its code.'});answer(400,'Sign-in could not be confirmed. Return to Studio.');}
  finally{finished=true;finish();}
 };
 const server=createServer(async(request,response)=>{
  response.setHeader('Cache-Control','no-store');response.setHeader('Referrer-Policy','no-referrer');response.setHeader('Content-Security-Policy',"default-src 'none'");
  const answer=(code,text)=>{response.writeHead(code,{'Content-Type':'text/plain; charset=utf-8'});response.end(text);};
  if(request.method!=='GET'||request.headers.host!=='127.0.0.1:'+server.address().port||(request.url?.length??0)>16384){answer(400,'Invalid callback.');return;}
  await receive('http://127.0.0.1:'+server.address().port+request.url,answer);
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
 const callback='http://127.0.0.1:'+server.address().port+'/auth/callback';
 const params={client_id:client,ext_agent_host_id:hostId,response_type:'code',redirect_uri:callback,scope:required.join(' '),resource,
  state,nonce,...(config.requestConsent||original&&!original.scopes?.includes('chatgpt.tokens.use.direct')?{prompt:'consent'}:{}),code_challenge_method:'S256',code_challenge:createHash('sha256').update(verifier).digest('base64url'),...(client==='dynamic_agent_client'?{agent_name_hint:'R4OS Studio'}:{})};
 const authorizationUrl=issuer+'/api/accounts/authorize?'+new URLSearchParams(params);
 await status({state:'waiting',authorizationUrl,expiresAt:new Date(Date.now()+600000).toISOString()});
 console.log(JSON.stringify({state:'waiting',authorizationUrl}));
 // The web backend forwards an explicitly pasted redirect through this same
 // private process pipe. Both delivery paths consume the same original PKCE.
 const commands=(async()=>{
  for await(const line of input){
   if(finished)break;
   try{
    if(Buffer.byteLength(line)>32768)throw Error();
    const value=JSON.parse(line);
    if(Object.keys(value).length!==1||typeof value.callbackUrl!=='string')throw Error();
    await receive(value.callbackUrl,()=>{});
   }catch{if(!consumed&&!finished)await status({callbackError:'Invalid redirect input.'});}
  }
 })();
 timer=setTimeout(()=>{finished=true;void status({state:'expired'}).finally(finish);},600000);
 const cancel=()=>{finished=true;void status({state:consumed?'unknown':'cancelled'}).finally(finish);};
 process.once('SIGTERM',cancel);process.once('SIGINT',cancel);
 await completed;clearTimeout(timer);server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
 input.return?.();
 void commands.catch(()=>{});
}
let config;
const reader=createInterface({input:process.stdin,crlfDelay:Infinity}),input=reader[Symbol.asyncIterator]();
try {
 if(process.argv.length!==2)throw Error('server_account_operation_only');
 const first=await input.next();
 if(first.done||Buffer.byteLength(first.value)>262144)throw Error('auth_input_limit');
 config=JSON.parse(first.value);
 await main(config,input);
}catch(error){
 if(config?.statusPath){let previous={};try{previous=await privateFile(config.statusPath);}catch{/* Preserve the new failure even if its prior journal cannot be read. */}await atomic(config.statusPath,{...previous,state:'unknown',...(error.originalError?{originalError:error.originalError}:{}),error:'The original account operation was not confirmed. No automatic retry.',updatedAt:new Date().toISOString()}).catch(()=>{});}
 console.error('The original ChatGPT account operation could not be confirmed.');process.exitCode=1;
}finally{reader.close();process.stdin.destroy();}
