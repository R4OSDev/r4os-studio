import {createHmac,randomBytes,timingSafeEqual} from 'node:crypto';
import { join } from 'node:path';
import type {GitHubProjectBinding} from '../../../../shared/project-github.js';
import type {GitHubIssue,GitHubIssuePage,GitHubIssueState} from '../../../../shared/project-github-issues.js';
import {GitHubApi,GitHubRateLimit,ownerName,repoName,retryAt} from '../github-connections/repositories.js';
import {GitHubStore} from '../github-connections/store.js';
import {ProjectError} from '../projects/store.js';
import {bindingKey,GitHubObservations,observationKey} from './observations.js';
import type {SavedIssuePage} from './observations.js';
import { githubDirectory, readGitHubJson, saveGitHubJson, withGitHubLock } from '../github-connections/private-storage.js';

// The browser cannot submit a query, repository target, URL or mutation.
export const ISSUES_QUERY=`query StudioProjectIssues($owner:String!,$name:String!,$states:[IssueState!],$after:String){
  viewer{databaseId}
  repository(owner:$owner,name:$name){databaseId nameWithOwner hasIssuesEnabled
    openIssues:issues(first:1,states:[OPEN]){totalCount}
    issuePage:issues(first:25,states:$states,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){
      nodes{__typename id number title state url updatedAt labels(first:12){nodes{name color} totalCount}}
      pageInfo{hasNextPage endCursor}
    }
  }
}`;
type BindingReader=(id:string)=>Promise<GitHubProjectBinding|null>;
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&(v as number)>=0;
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length>0&&v.length<=max&&!/[\p{Cc}\p{Cs}]/u.test(v);
const invalid=()=>new ProjectError('GitHub returned incomplete or invalid issue data. Refresh without treating the count as zero.',502);
type RawIssue={__typename?:unknown;id?:unknown;number?:unknown;title?:unknown;state?:unknown;url?:unknown;updatedAt?:unknown;labels?:{nodes?:{name?:unknown;color?:unknown}[];totalCount?:unknown}};
type QueryResult={errors?:{type?:string;extensions?:{type?:string;code?:string}}[];data?:{
  viewer?:{databaseId?:unknown};repository?:{databaseId?:unknown;nameWithOwner?:unknown;hasIssuesEnabled?:unknown;
    openIssues?:{totalCount?:unknown};issuePage?:{nodes?:RawIssue[];pageInfo?:{hasNextPage?:unknown;endCursor?:unknown}}}|null}};
type Cached={connection:string;value:GitHubIssuePage};
class SupersededRead extends ProjectError {constructor(){super('Issue access changed during this read. Refresh its issues.',409);}}

export class GitHubIssues {
  private cache=new Map<string,Cached>();
  private pending=new Map<string,Promise<GitHubIssuePage>>();
  private secret=randomBytes(32);
  private access=new Map<string,{revision:number;readers:number}>();
  private throttled=new Map<number,number>();
  constructor(private store:GitHubStore,private readBinding:BindingReader,private transport:typeof fetch=fetch,
    readonly observations?:GitHubObservations,private maxAge:()=>Promise<number>=async()=>3600_000){}
  private async cooldown(userId:number){
    if(!this.observations)return 0;
    const value=await readGitHubJson<{retryAt:number}>(join(this.observations.directory,'limit-'+userId+'.json'));
    return Math.max(this.throttled.get(userId)??0,value?.retryAt??0);
  }
  async onCooldown(userId:number){return (await this.cooldown(userId))>Date.now();}
  private async rememberLimit(userId:number,retryAt:number){
    if(!this.observations)return;
    this.throttled.set(userId,retryAt);
    await githubDirectory(this.observations.directory);
    const path=join(this.observations.directory,'limit-'+userId+'.json');
    await withGitHubLock(path+'.lock',async()=>{
      const existing=await readGitHubJson<{retryAt:number}>(path);
      if(!existing||existing.retryAt<retryAt)await saveGitHubJson(path,{retryAt});
    });
  }
  private clear(connection:string){for(const [key,v] of this.cache)if(v.connection===connection)this.cache.delete(key);}
  private sign(raw:string){return createHmac('sha256',this.secret).update(raw).digest();}
  private cursor(value:string|null,scope:string,state:GitHubIssueState):string|null {
    if(value===null)return null;
    try{
      const [raw,signature,...extra]=value.split('.'),actual=Buffer.from(signature??'','base64url');
      if(extra.length||actual.length!==32||!timingSafeEqual(actual,this.sign(raw)))throw Error();
      const data=JSON.parse(Buffer.from(raw,'base64url').toString('utf8'));
      if(data.scope!==scope||data.state!==state||!integer(data.expires)||data.expires<Date.now()||!text(data.after,2048))throw Error();
      return data.after;
    }catch{throw new ProjectError('The issue page expired or belongs to an earlier repository, connection or filter. Refresh from the first page.',409);}
  }
  private next(after:string,scope:string,state:GitHubIssueState){
    const raw=Buffer.from(JSON.stringify({after,scope,state,expires:Date.now()+600_000})).toString('base64url');
    return raw+'.'+this.sign(raw).toString('base64url');
  }
  private async context(id:string,revision:number){
    const bound=await this.readBinding(id);
    if(!bound)throw new ProjectError('Connect a repository to view its issues.',409);
    if(bound.revision!==revision)throw new ProjectError('The repository connection changed. Refresh its issues.',409);
    if(!ownerName(bound.repository.owner)||!repoName(bound.repository.name))throw new ProjectError('The repository binding needs attention.',409);
    const credential=await this.store.credential(bound.connectionId),credentialRevision=credential.connection.tokenRevision!;
    return {bound,credentialRevision,scope:observationKey(id,bound,credentialRevision),token:credential.token};
  }
  private async page(value:SavedIssuePage,scope:string,cached:boolean,error?:string):Promise<GitHubIssuePage>{
    const {after,...fields}=value;
    const expires=Date.parse(fields.checkedAt)+(this.observations?await this.maxAge():30_000);
    return {...fields,nextCursor:after?this.next(after,scope,value.state):null,expiresAt:new Date(Math.min(expires,8.64e15)).toISOString(),
      cached,stale:!!error||Date.now()>=expires,...(error?{refreshError:error}:{})};
  }
  async saved(id:string,revision:number):Promise<GitHubIssuePage|null>{
    const {bound,credentialRevision,scope}=await this.context(id,revision);
    const saved=await this.observations?.issues(id,scope);
    if(!saved?.value?.openPage){
      if(saved?.error)throw new ProjectError(saved.error,503);
      return null;
    }
    if((await this.context(id,revision)).scope!==scope)throw new SupersededRead();
    await this.store.assertCredential(bound.connectionId,credentialRevision);
    return this.page({...saved.value.openPage,openCount:saved.value.openCount},scope,true,saved.error);
  }
  async read(id:string,revision:number,state:GitHubIssueState,cursor:string|null,refresh=false):Promise<GitHubIssuePage>{
    const {bound,credentialRevision,scope,token}=await this.context(id,revision);
    const binding=bindingKey(bound);
    const after=this.cursor(cursor,scope,state),key=JSON.stringify([scope,state,after]);
    let access=this.access.get(bound.connectionId);
    if(!access){access={revision:0,readers:0};this.access.set(bound.connectionId,access);}
    access.readers++;const admitted=access.revision;
    const assertCurrent=async()=>{
      await this.store.assertCredential(bound.connectionId,credentialRevision);
      const current=await this.readBinding(id);
      if(!current||bindingKey(current)!==binding)throw new ProjectError('The repository connection changed during the issue read. Refresh its issues.',409);
      if(access.revision!==admitted)throw new SupersededRead();
    };
    try{
      const saved=this.cache.get(key);
      if(!refresh&&saved&&Date.parse(saved.value.checkedAt)+30_000>Date.now()){
        await assertCurrent();return {...saved.value,cached:true};
      }
      const retry=await this.cooldown(bound.userId);
      let request=this.pending.get(key);
      if(!request){
        if(this.pending.size>=4)throw new ProjectError('GitHub issue reads are busy. Retry shortly.',429);
        const started=Date.now();
        if(retry>started)throw new GitHubRateLimit(retry);
        this.throttled.delete(bound.userId);
        request=(async()=>{
          try{
            const observed=await this.fetch(id,bound,token,credentialRevision,state,after);
            await assertCurrent();
            await this.observations?.saveIssues(id,scope,started,observed,state==='open'&&after===null);
            const value=await this.page(observed,scope,false);
            this.cache.delete(key);this.cache.set(key,{connection:bound.connectionId,value});
            while(this.cache.size>64)this.cache.delete(this.cache.keys().next().value!);
            return value;
          }catch(error){
            if(error instanceof GitHubRateLimit)await this.rememberLimit(bound.userId,error.retryAt);
            if(error instanceof ProjectError&&!(error instanceof SupersededRead)){
              const revoke=[401,403,404,409,422].includes(error.statusCode);
              if(revoke)access.revision++;
              await this.observations?.issueFailure(id,scope,revoke?Date.now():started,error.message,revoke);
            }
            throw error;
          }
        })();
        this.pending.set(key,request);
        void request.finally(()=>{if(this.pending.get(key)===request)this.pending.delete(key);}).catch(()=>undefined);
      }
      const result=await request;await assertCurrent();return result;
    }catch(error){
      this.clear(bound.connectionId);
      throw error;
    }finally{if(--access.readers===0)this.access.delete(bound.connectionId);}
  }
  private async fetch(id:string,bound:GitHubProjectBinding,token:string,credentialRevision:number,state:GitHubIssueState,after:string|null):Promise<SavedIssuePage>{
    let limit:Headers|undefined;
    const raw=await new GitHubApi(token,this.transport).request('/graphql','POST',{
      operationName:'StudioProjectIssues',query:ISSUES_QUERY,
      variables:{owner:bound.repository.owner,name:bound.repository.name,states:state==='all'?null:[state.toUpperCase()],after}
    },headers=>{limit=headers;}) as QueryResult;
    if(!raw||typeof raw!=='object')throw invalid();
    if(raw.errors!==undefined){
      if(!Array.isArray(raw.errors))throw invalid();
      if(raw.errors.length){
        const kinds=raw.errors.map(e=>e?.type??e?.extensions?.type??e?.extensions?.code);
        if(kinds.some(v=>v==='RATE_LIMITED')||limit?.get('x-ratelimit-remaining')==='0'||limit?.has('retry-after'))
          throw new GitHubRateLimit(limit?retryAt(limit):undefined);
        if(kinds.some(v=>v==='FORBIDDEN'||v==='INSUFFICIENT_SCOPES'||v==='UNAUTHORIZED'))throw new ProjectError('GitHub denied issue access. Check this connection’s Issues read permission and SSO.',403);
        throw new ProjectError('GitHub returned an incomplete issue query. Partial data and counts were discarded.',502);
      }
    }
    const repo=raw.data?.repository,viewer=raw.data?.viewer;
    if(viewer?.databaseId!==bound.userId)throw new ProjectError('This connection authenticates a different or unconfirmed account. Reconnect explicitly.',409);
    if(!repo)throw new ProjectError('The repository is unavailable to this connection. Check issue access.',404);
    const name=bound.repository.owner+'/'+bound.repository.name;
    if(repo.databaseId!==bound.repository.id||typeof repo.nameWithOwner!=='string'||repo.nameWithOwner.toLowerCase()!==name.toLowerCase())throw new ProjectError('The repository identity changed. Reconnect explicitly.',409);
    if(repo.hasIssuesEnabled===false)throw new ProjectError('GitHub Issues are disabled for this repository.',422);
    const page=repo.issuePage,info=page?.pageInfo;
    if(repo.hasIssuesEnabled!==true||!integer(repo.openIssues?.totalCount)||!page||!Array.isArray(page.nodes)||page.nodes.length>25||!info||typeof info.hasNextPage!=='boolean'||(info.hasNextPage&&!text(info.endCursor,2048)))throw invalid();
    const items:GitHubIssue[]=page.nodes.map(v=>{
      if(!v||v.__typename!=='Issue'||!integer(v.number)||v.number<1||!text(v.title,1024)||!['OPEN','CLOSED'].includes(String(v.state))||!text(v.updatedAt,64)||!Number.isFinite(Date.parse(v.updatedAt))||!v.labels||!Array.isArray(v.labels.nodes)||v.labels.nodes.length>12||!integer(v.labels.totalCount)||v.labels.totalCount<v.labels.nodes.length)throw invalid();
      const issueState=v.state==='OPEN'?'open':'closed',url='https://github.com/'+repo.nameWithOwner+'/issues/'+v.number;
      if(v.url!==url||(state!=='all'&&state!==issueState))throw invalid();
      const labels=v.labels.nodes.map(l=>{if(!text(l.name,100)||typeof l.color!=='string'||! /^[a-f0-9]{6}$/i.test(l.color))throw invalid();return{name:l.name,color:l.color};});
      const id=typeof v.id==='string'&&/^[A-Za-z0-9_+/=-]{1,256}$/.test(v.id)?v.id:undefined;
      if(v.id!==undefined&&!id)throw invalid();
      return{number:v.number,title:v.title,state:issueState,url,updatedAt:v.updatedAt,labels,moreLabels:v.labels.totalCount-labels.length,...(id?{id}:{})};
    });
    if(new Set(items.map(v=>v.number)).size!==items.length||info.hasNextPage&&(!items.length||info.endCursor===after))throw invalid();
    const now=Date.now();
    return{scope:{projectId:id,repositoryId:bound.repository.id,bindingRevision:bound.revision,credentialRevision},repository:repo.nameWithOwner,state,items,openCount:repo.openIssues!.totalCount as number,
      after:info.hasNextPage?info.endCursor as string:null,checkedAt:new Date(now).toISOString()};
  }
}
