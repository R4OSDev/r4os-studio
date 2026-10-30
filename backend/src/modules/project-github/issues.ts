import {createHash,createHmac,randomBytes,timingSafeEqual} from 'node:crypto';
import type {GitHubProjectBinding} from '../../../../shared/project-github.js';
import type {GitHubIssue,GitHubIssuePage,GitHubIssueState} from '../../../../shared/project-github-issues.js';
import {GitHubApi,ownerName,repoName} from '../github-connections/repositories.js';
import {GitHubStore} from '../github-connections/store.js';
import {ProjectError} from '../projects/store.js';

// The browser cannot submit a query, repository target, URL or mutation.
export const ISSUES_QUERY=`query StudioProjectIssues($owner:String!,$name:String!,$states:[IssueState!],$after:String){
  viewer{databaseId}
  repository(owner:$owner,name:$name){databaseId nameWithOwner hasIssuesEnabled
    openIssues:issues(first:1,states:[OPEN]){totalCount}
    issuePage:issues(first:25,states:$states,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){
      nodes{__typename number title state url updatedAt labels(first:12){nodes{name color} totalCount}}
      pageInfo{hasNextPage endCursor}
    }
  }
}`;
type BindingReader=(id:string)=>Promise<GitHubProjectBinding|null>;
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&(v as number)>=0;
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length>0&&v.length<=max&&!/[\p{Cc}\p{Cs}]/u.test(v);
const bindingKey=(v:GitHubProjectBinding)=>JSON.stringify([v.revision,v.connectionId,v.userId,v.repository.id,v.repository.owner,v.repository.name,v.branch]);
const invalid=()=>new ProjectError('GitHub returned incomplete or invalid issue data. Refresh without treating the count as zero.',502);
type RawIssue={__typename?:unknown;number?:unknown;title?:unknown;state?:unknown;url?:unknown;updatedAt?:unknown;labels?:{nodes?:{name?:unknown;color?:unknown}[];totalCount?:unknown}};
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
  constructor(private store:GitHubStore,private readBinding:BindingReader,private transport:typeof fetch=fetch){}
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
  async read(id:string,revision:number,state:GitHubIssueState,cursor:string|null,refresh=false):Promise<GitHubIssuePage>{
    const bound=await this.readBinding(id);
    if(!bound)throw new ProjectError('Connect a repository to view its issues.',409);
    if(bound.revision!==revision)throw new ProjectError('The repository connection changed. Refresh its issues.',409);
    if(!ownerName(bound.repository.owner)||!repoName(bound.repository.name))throw new ProjectError('The repository binding needs attention.',409);
    const credential=await this.store.credential(bound.connectionId),credentialRevision=credential.connection.tokenRevision!;
    const binding=bindingKey(bound),scope=createHash('sha256').update(JSON.stringify([id,binding,credentialRevision])).digest('hex');
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
      if(!refresh&&saved&&Date.parse(saved.value.expiresAt)>Date.now()){
        await assertCurrent();return {...saved.value,cached:true};
      }
      let request=this.pending.get(key);
      if(!request){
        if(this.pending.size>=4)throw new ProjectError('GitHub issue reads are busy. Retry shortly.',429);
        request=this.fetch(id,bound,credential.token,credentialRevision,state,after,scope).then(async value=>{
          await assertCurrent();this.cache.delete(key);this.cache.set(key,{connection:bound.connectionId,value});
          while(this.cache.size>64)this.cache.delete(this.cache.keys().next().value!);
          return value;
        });
        this.pending.set(key,request);
        void request.finally(()=>{if(this.pending.get(key)===request)this.pending.delete(key);}).catch(()=>undefined);
      }
      const result=await request;await assertCurrent();return result;
    }catch(error){
      this.clear(bound.connectionId);
      if(error instanceof ProjectError&&!(error instanceof SupersededRead)&&[401,403,404,409].includes(error.statusCode))access.revision++;
      throw error;
    }finally{if(--access.readers===0)this.access.delete(bound.connectionId);}
  }
  private async fetch(id:string,bound:GitHubProjectBinding,token:string,credentialRevision:number,state:GitHubIssueState,after:string|null,scope:string):Promise<GitHubIssuePage>{
    const raw=await new GitHubApi(token,this.transport).request('/graphql','POST',{
      operationName:'StudioProjectIssues',query:ISSUES_QUERY,
      variables:{owner:bound.repository.owner,name:bound.repository.name,states:state==='all'?null:[state.toUpperCase()],after}
    }) as QueryResult;
    if(!raw||typeof raw!=='object')throw invalid();
    if(raw.errors!==undefined){
      if(!Array.isArray(raw.errors))throw invalid();
      if(raw.errors.length){
        const kinds=raw.errors.map(e=>e?.type??e?.extensions?.type??e?.extensions?.code);
        if(kinds.some(v=>v==='RATE_LIMITED'))throw new ProjectError('GitHub issue rate limit reached. Retry later.',429);
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
      return{number:v.number,title:v.title,state:issueState,url,updatedAt:v.updatedAt,labels,moreLabels:v.labels.totalCount-labels.length};
    });
    if(new Set(items.map(v=>v.number)).size!==items.length||info.hasNextPage&&(!items.length||info.endCursor===after))throw invalid();
    const now=Date.now();
    return{scope:{projectId:id,repositoryId:bound.repository.id,bindingRevision:bound.revision,credentialRevision},repository:repo.nameWithOwner,state,items,openCount:repo.openIssues!.totalCount as number,
      nextCursor:info.hasNextPage?this.next(info.endCursor as string,scope,state):null,checkedAt:new Date(now).toISOString(),expiresAt:new Date(now+30_000).toISOString(),cached:false};
  }
}
