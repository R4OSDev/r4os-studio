import {useCallback,useEffect,useState} from 'react';
import type {GitHubProjectBinding} from '../../../../shared/project-github';
import type {GitHubIssuePage,GitHubIssueState} from '../../../../shared/project-github-issues';
import {projectRequest} from '../projects/api';

interface Selection{id:string|null;state:GitHubIssueState;cursor:string|null;previous:(string|null)[];revision:number;mode:'saved'|'remote'|'refresh'}
interface Read {id:string|null;key:string;binding:GitHubProjectBinding|null|undefined;data?:GitHubIssuePage;error:string}
export function useProjectIssues(id:string|null){
  const [selection,setSelection]=useState<Selection>({id,state:'open',cursor:null,previous:[],revision:0,mode:'saved'});
  if(selection.id!==id)setSelection({id,state:'open',cursor:null,previous:[],revision:selection.revision+1,mode:'saved'});
  const key=JSON.stringify([id,selection.state,selection.cursor,selection.revision]);
  const [read,setRead]=useState<Read>({id:null,key:'',binding:undefined,error:''});
  const [expired,setExpired]=useState('');
  const refresh=useCallback(()=>setSelection(v=>({...v,cursor:null,previous:[],revision:v.revision+1,mode:'refresh'})),[]);
  const loadSaved=useCallback(()=>setSelection(v=>({...v,state:'open',cursor:null,previous:[],revision:v.revision+1,mode:'saved'})),[]);
  useEffect(()=>{
    if(!id)return;
    const controller=new AbortController();
    void(async()=>{
      let binding:GitHubProjectBinding|null|undefined;
      try{
        const local=await projectRequest<{binding:GitHubProjectBinding|null}>(`/${id}/github`,'','GET',undefined,controller.signal);
        if(controller.signal.aborted)return;
        binding=local.binding;
        if(!binding){setRead({id,key,binding:null,error:''});return;}
        const query=new URLSearchParams({bindingRevision:String(binding.revision),state:selection.state});
        if(selection.cursor)query.set('cursor',selection.cursor);
        if(selection.mode==='refresh')query.set('refresh','true');
        setRead({id,key:'pending:'+key,binding,error:''});
        const data=selection.mode==='saved'
          ? (await projectRequest<{page:GitHubIssuePage|null}>(`/${id}/github/issues/saved?bindingRevision=${binding.revision}`,'','GET',undefined,controller.signal)).page
          : await projectRequest<GitHubIssuePage>(`/${id}/github/issues?${query}`,'','GET',undefined,controller.signal);
        if(controller.signal.aborted)return;
        if(!data){setRead({id,key,binding,error:''});return;}
        if(data.scope.projectId!==id||data.scope.repositoryId!==binding.repository.id||data.scope.bindingRevision!==binding.revision||data.state!==selection.state||!Number.isSafeInteger(data.openCount)||data.openCount<0||!Array.isArray(data.items)||data.items.length>25)throw Error('The issue response could not be matched to this repository. Refresh its issues.');
        if(new Set(data.items.map(v=>v.number)).size!==data.items.length)throw Error('The issue page contains duplicate entries. Refresh its issues.');
        setRead({id,key,binding,data,error:''});
      }catch(error){if(!controller.signal.aborted)setRead({id,key,binding,error:(error as Error).message});}
    })();
    return()=>controller.abort();
  },[id,key,selection.state,selection.cursor,selection.mode]);
  useEffect(()=>{
    if(!id)return;
    const changed=(event:Event)=>{if((event as CustomEvent).detail?.projectId===id)loadSaved();};
    window.addEventListener('studio-project-github-changed',changed);
    return()=>window.removeEventListener('studio-project-github-changed',changed);
  },[id,loadSaved]);
  const same=read.id===id,data=same&&read.key===key?read.data:undefined;
  useEffect(()=>{
    if(!data)return;
    const expires=Date.parse(data.expiresAt)-Date.now();
    if(expires>2_147_483_647)return;
    const timer=setTimeout(()=>setExpired(data.checkedAt),Math.max(0,expires));
    return()=>clearTimeout(timer);
  },[data]);
  return{
    binding:same?read.binding:undefined,data,error:same&&read.key===key?read.error:'',
    loading:!!id&&(!same||read.key!==key),stale:!!data&&(data.stale||expired===data.checkedAt),
    state:selection.state,canPrevious:selection.previous.length>0,
    filter:(state:GitHubIssueState)=>setSelection(v=>({...v,state,cursor:null,previous:[],revision:v.revision+1,mode:'remote'})),
    next:()=>{if(data?.nextCursor)setSelection(v=>({...v,cursor:data.nextCursor,previous:[...v.previous,v.cursor].slice(-50),revision:v.revision+1,mode:'remote'}));},
    previous:()=>setSelection(v=>v.previous.length?{...v,cursor:v.previous.at(-1)!,previous:v.previous.slice(0,-1),revision:v.revision+1,mode:'remote'}:v),refresh
  };
}
export type ProjectIssuesModel=ReturnType<typeof useProjectIssues>;
