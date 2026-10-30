import {useCallback,useEffect,useRef,useState} from 'react';
import type {ScreenshotPage} from '../../../../shared/agent-sessions';
import {ProjectRequestError,sessionPath,useSessionApi} from './api';

const uuid=/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function matches(page:ScreenshotPage,scope:string,owner:string,sid:string) {
  const seen=new Set<string>();
  return page?.schema===1&&page.sessionId===sid&&page.owner?.type===scope&&page.owner.id===owner
    &&typeof page.available==='boolean'&&Number.isSafeInteger(page.revision)&&page.revision>=0&&Number.isSafeInteger(page.watermark)&&page.watermark>=0
    &&typeof page.coverage?.complete==='boolean'&&Number.isSafeInteger(page.coverage.unqualified)&&page.coverage.unqualified>=0
    &&(page.nextCursor===null||typeof page.nextCursor==='string'&&page.nextCursor.length<=1024)
    &&Array.isArray(page.items)&&page.items.length<=32&&page.items.every((v,i)=>{
      if(!v||v.sessionId!==sid||v.projectId!==owner||!uuid.test(v.id)||!uuid.test(v.jobId)||seen.has(v.id)
        ||v.source!=='agent-vm-capture'||!Number.isSafeInteger(v.publication)||v.publication<=0||i>0&&page.items[i-1].publication<=v.publication)return false;
      seen.add(v.id);return true;
    });
}
export function useScreenshotGallery(ownerId:string,sessionId:string,reauth:()=>Promise<void>) {
  const {request,scope}=useSessionApi(),path=sessionPath(ownerId,sessionId)+'/screenshots',key=scope+path;
  const following=useRef(true);
  const [selection,setSelection]=useState<{key:string;cursor:string|null;back:(string|null)[];epoch:number}>({key,cursor:null,back:[],epoch:0});
  const current=selection.key===key?selection:{key,cursor:null,back:[],epoch:0};
  const [state,setState]=useState<{key:string;page:ScreenshotPage|null;latest:ScreenshotPage['items'][number]|null;busy:boolean;error:string;authLost:boolean}>({key,page:null,latest:null,busy:true,error:'',authLost:false});
  useEffect(()=>{
    let ended=false,loading=false,first=true,timer:number|undefined,active:AbortController|null=null,failures=0,denied=false,wakeRequested=false;
    setState(old=>({...old,key,page:old.key===key?old.page:null,latest:old.key===key?old.latest:null,busy:true,error:'',authLost:old.key===key&&old.authLost}));
    const load=async()=>{
      if(ended||loading||document.hidden||denied)return;
      window.clearTimeout(timer);
      loading=true;const controller=new AbortController();active=controller;
      const initial=first;
      try {
        const incoming=await request<ScreenshotPage>(path+(initial&&current.cursor?'?cursor='+encodeURIComponent(current.cursor):''),'','GET',undefined,controller.signal);
        if(controller.signal.aborted||ended)return;
        if(!matches(incoming,scope,ownerId,sessionId))throw Error('The screenshot response could not be verified for this session.');
        failures=0;first=false;
        setState(old=>{
          const previous=old.key===key?old:null;
          const page=initial||!current.cursor&&following.current||!previous?.page?incoming:{...previous.page,coverage:incoming.coverage};
          const latest=initial&&current.cursor?previous?.latest??null:incoming.coverage.complete?incoming.items[0]??null:previous?.latest??null;
          const next={key,page,latest,busy:false,error:'',authLost:false};
          return JSON.stringify(old)===JSON.stringify(next)?old:next;
        });
        timer=window.setTimeout(()=>{void load();},incoming.coverage.complete?2000:500);
      }catch(error){
        if(controller.signal.aborted||ended)return;
        const status=(error as ProjectRequestError).status??0;failures++;
        if(status===409&&current.cursor){setSelection(old=>({key,cursor:null,back:[],epoch:old.epoch+1}));return;}
        denied=[401,403,404,410].includes(status);
        setState(old=>({...old,key,busy:false,error:[401,403].includes(status)?'Sign-in expired. Refresh your session and retry.':(error as Error).message,authLost:denied}));
        if([401,403].includes(status))void reauth().catch(()=>undefined);
        if(!denied)timer=window.setTimeout(()=>{void load();},Math.min(15000,2000*failures));
      }finally{
        loading=false;if(active===controller)active=null;
        if(wakeRequested&&!document.hidden&&!ended&&!denied){wakeRequested=false;void load();}
      }
    };
    const wake=()=>{
      window.clearTimeout(timer);
      if(document.hidden){active?.abort();return;}
      if(loading){wakeRequested=true;return;}
      if(!denied)void load();
    };
    void load();document.addEventListener('visibilitychange',wake);window.addEventListener('focus',wake);window.addEventListener('online',wake);
    return()=>{ended=true;active?.abort();window.clearTimeout(timer);document.removeEventListener('visibilitychange',wake);window.removeEventListener('focus',wake);window.removeEventListener('online',wake);};
  },[key,path,ownerId,sessionId,scope,current.cursor,current.epoch,request,reauth]);
  const latest=useCallback(()=>{following.current=true;setSelection(old=>({key,cursor:null,back:[],epoch:old.epoch+1}));},[key]);
  return {...(state.key===key?state:{key,page:null,latest:null,busy:true,error:'',authLost:false}),
    hasNewer:current.back.length>0,windowKey:key+':'+(current.cursor??'latest'),hold:()=>{following.current=false;},
    older:()=>{if(state.page?.nextCursor&&!state.busy)setSelection({...current,cursor:state.page.nextCursor,back:[...current.back,current.cursor]});},
    newer:()=>{if(current.back.length&&!state.busy)setSelection({...current,cursor:current.back.at(-1)!,back:current.back.slice(0,-1)});},
    refresh:()=>setSelection({...current,epoch:current.epoch+1}),showLatest:latest};
}
