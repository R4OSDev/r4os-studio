import {useCallback,useEffect,useState} from 'react';
import type {ScreenshotPage} from '../../../../shared/agent-sessions';
import {ProjectRequestError,sessionPath,useSessionApi} from './api';

export function useScreenshotGallery(ownerId:string,sessionId:string,reauth:()=>Promise<void>) {
  const {request,scope}=useSessionApi(),path=sessionPath(ownerId,sessionId)+'/screenshots',key=scope+path;
  const [selection,setSelection]=useState<{key:string;cursor:string|null;back:(string|null)[];epoch:number}>({key,cursor:null,back:[],epoch:0});
  const current=selection.key===key?selection:{key,cursor:null,back:[],epoch:0};
  const [state,setState]=useState<{key:string;page:ScreenshotPage|null;latest:ScreenshotPage['items'][number]|null;busy:boolean;error:string;authLost:boolean}>({key,page:null,latest:null,busy:true,error:'',authLost:false});
  useEffect(()=>{
    const controller=new AbortController();let timer:number|undefined;
    setState(old=>({...old,key,page:old.key===key?old.page:null,latest:old.key===key?old.latest:null,busy:true,error:'',authLost:false}));
    const load=async()=>{
      try {
        const page=await request<ScreenshotPage>(path+(current.cursor?'?cursor='+encodeURIComponent(current.cursor):''),'','GET',undefined,controller.signal);
        if(controller.signal.aborted)return;
        if(!page||page.schema!==1||page.sessionId!==sessionId||page.owner?.type!==scope||page.owner.id!==ownerId||!Array.isArray(page.items)||page.items.length>32
          ||page.items.some(v=>v.sessionId!==sessionId||v.projectId!==ownerId))throw Error('The screenshot response belongs to another session.');
        setState(old=>({key,page,latest:current.cursor?old.key===key?old.latest:null:page.items[0]??null,busy:false,error:'',authLost:false}));
        if(!page.coverage.complete)timer=window.setTimeout(()=>{void load();},500);
      }catch(error){
        if(controller.signal.aborted)return;
        const authLost=[401,403].includes((error as ProjectRequestError).status??0);
        setState(old=>({...old,key,busy:false,error:authLost?'Sign-in expired. Refresh your session and retry.':(error as Error).message,authLost}));
        if(authLost)void reauth().catch(()=>undefined);
      }
    };
    void load();return()=>{controller.abort();window.clearTimeout(timer);};
  },[key,path,ownerId,sessionId,scope,current.cursor,current.epoch,request,reauth]);
  const latest=useCallback(()=>setSelection(old=>({key,cursor:null,back:[],epoch:old.epoch+1})),[key]);
  return {...(state.key===key?state:{key,page:null,latest:null,busy:true,error:'',authLost:false}),
    hasNewer:current.back.length>0,windowKey:key+':'+(current.cursor??'latest'),
    older:()=>{if(state.page?.nextCursor&&!state.busy)setSelection({...current,cursor:state.page.nextCursor,back:[...current.back,current.cursor]});},
    newer:()=>{if(current.back.length&&!state.busy)setSelection({...current,cursor:current.back.at(-1)!,back:current.back.slice(0,-1)});},
    refresh:()=>setSelection({...current,epoch:current.epoch+1}),showLatest:latest};
}
