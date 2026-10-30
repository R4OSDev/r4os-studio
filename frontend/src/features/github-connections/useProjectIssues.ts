import {useCallback,useEffect,useState} from 'react';
import type {GitHubProjectBinding} from '../../../../shared/project-github';
import type {GitHubIssuePage,GitHubIssueState} from '../../../../shared/project-github-issues';
import {projectRequest} from '../projects/api';

interface Selection{id:string|null;state:GitHubIssueState;cursor:string|null;previous:(string|null)[];revision:number;refresh:boolean}
interface Read {id:string|null;key:string;binding:GitHubProjectBinding|null|undefined;data?:GitHubIssuePage;error:string}
export function useProjectIssues(id:string|null){
  const [selection,setSelection]=useState<Selection>({id,state:'open',cursor:null,previous:[],revision:0,refresh:false});
  if(selection.id!==id)setSelection({id,state:'open',cursor:null,previous:[],revision:selection.revision+1,refresh:false});
  const key=JSON.stringify([id,selection.state,selection.cursor,selection.revision]);
  const [read,setRead]=useState<Read>({id:null,key:'',binding:undefined,error:''});
  const [expired,setExpired]=useState('');
  const refresh=useCallback(()=>setSelection(v=>({...v,cursor:null,previous:[],revision:v.revision+1,refresh:true})),[]);
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
        if(selection.refresh)query.set('refresh','true');
        setRead({id,key:'pending:'+key,binding,error:''});
        const data=await projectRequest<GitHubIssuePage>(`/${id}/github/issues?${query}`,'','GET',undefined,controller.signal);
        if(controller.signal.aborted)return;
        if(data.scope.projectId!==id||data.scope.repositoryId!==binding.repository.id||data.scope.bindingRevision!==binding.revision||data.state!==selection.state||!Number.isSafeInteger(data.openCount)||data.openCount<0||!Array.isArray(data.items)||data.items.length>25)throw Error('The issue response could not be matched to this repository. Refresh its issues.');
        if(new Set(data.items.map(v=>v.number)).size!==data.items.length)throw Error('The issue page contains duplicate entries. Refresh its issues.');
        setRead({id,key,binding,data,error:''});
      }catch(error){if(!controller.signal.aborted)setRead({id,key,binding,error:(error as Error).message});}
    })();
    return()=>controller.abort();
  },[id,key,selection.state,selection.cursor,selection.refresh]);
  useEffect(()=>{
    if(!id)return;
    const focus=()=>{if(!document.hidden)refresh();};
    const changed=(event:Event)=>{if((event as CustomEvent).detail?.projectId===id)refresh();};
    window.addEventListener('focus',focus);document.addEventListener('visibilitychange',focus);window.addEventListener('studio-project-github-changed',changed);
    return()=>{window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',focus);window.removeEventListener('studio-project-github-changed',changed);};
  },[id,refresh]);
  const same=read.id===id,data=same&&read.key===key?read.data:undefined;
  useEffect(()=>{
    if(!data)return;
    const timer=setTimeout(()=>setExpired(data.checkedAt),Math.max(0,Date.parse(data.expiresAt)-Date.now()));
    return()=>clearTimeout(timer);
  },[data]);
  return{
    binding:same?read.binding:undefined,data,error:same&&read.key===key?read.error:'',
    loading:!!id&&(!same||read.key!==key),stale:!!data&&expired===data.checkedAt,
    state:selection.state,canPrevious:selection.previous.length>0,
    filter:(state:GitHubIssueState)=>setSelection(v=>({...v,state,cursor:null,previous:[],revision:v.revision+1,refresh:false})),
    next:()=>{if(data?.nextCursor)setSelection(v=>({...v,cursor:data.nextCursor,previous:[...v.previous,v.cursor].slice(-50),revision:v.revision+1,refresh:false}));},
    previous:()=>setSelection(v=>v.previous.length?{...v,cursor:v.previous.at(-1)!,previous:v.previous.slice(0,-1),revision:v.revision+1,refresh:false}:v),refresh
  };
}
export type ProjectIssuesModel=ReturnType<typeof useProjectIssues>;
