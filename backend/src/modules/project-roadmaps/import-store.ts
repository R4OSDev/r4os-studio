import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {ProjectError} from '../projects/store.js';

/** Fixed binary adapter; the request never selects a host path or script. */
export function uploadRoadmapJson<T>(directory:string,input:Record<string,unknown>,bytes:Buffer):Promise<T>{
 return new Promise((resolve,reject)=>{
  const child=spawn('/usr/bin/python3',['-B',fileURLToPath(new URL('../../../../scripts/project-roadmaps/json_upload_cli.py',import.meta.url)),directory],{stdio:['pipe','pipe','ignore'],env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8'}});
  let output='',length=0,settled=false;
  const finish=(error?:Error,value?:T)=>{if(settled)return;settled=true;clearTimeout(timer);if(error)reject(error);else resolve(value!);};
  const timer=setTimeout(()=>{child.kill('SIGKILL');finish(new ProjectError('The original JSON upload is unconfirmed. Read its original file receipt.',503));},30000);
  child.on('error',()=>finish(new ProjectError('JSON upload support is unavailable.',503)));child.stdin.on('error',()=>{});
  child.stdout.setEncoding('utf8');child.stdout.on('data',(data:string)=>{output+=data;length+=Buffer.byteLength(data);if(length>131072){child.kill('SIGKILL');finish(new ProjectError('JSON file receipt exceeds its limit.',503));}});
  child.on('close',()=>{try{const value=JSON.parse(output);if(value.error)finish(new ProjectError(value.error,value.code));else if(Object.hasOwn(value,'result'))finish(undefined,value.result);else throw Error();}catch{finish(new ProjectError('The original JSON upload is unconfirmed. Read its original file receipt.',503));}});
  child.stdin.write(JSON.stringify(input)+'\n');child.stdin.end(bytes);
 });
}
