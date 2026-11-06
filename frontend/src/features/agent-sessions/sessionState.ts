import type {AgentSession} from '../../../../shared/agent-sessions';

/** Model saves must not roll a newer run, choice or measured context back. */
export function mergeSession(current:AgentSession|null,next:AgentSession):AgentSession {
  if(!current||current.id!==next.id||current.owner.id!==next.owner.id||current.owner.type!==next.owner.type)return next;
  const quotaWait=(current.quotaWait?.revision??0)>(next.quotaWait?.revision??0)?current.quotaWait:next.quotaWait;
  if(current.revision>next.revision||(current.selectionRevision??0)>(next.selectionRevision??0)
    ||(current.selectionStateRevision??0)>(next.selectionStateRevision??0))return quotaWait===current.quotaWait?current:{...current,quotaWait};
  const oldRun=current.latestRun,newRun=next.latestRun;
  const rank={queued:0,starting:1,running:2,stopping:3,completed:4,failed:4,interrupted:4,unknown:4};
  const keepRun=!!oldRun&&(!newRun||oldRun.createdAt>newRun.createdAt
    ||oldRun.id===newRun.id&&rank[oldRun.state]>rank[newRun.state]);
  const keepContext=!!current.context&&current.context.revision>(next.context?.revision??0);
  return {...next,...(quotaWait!==next.quotaWait?{quotaWait}:{}),...(keepRun?{latestRun:oldRun}:{}),...(keepContext?{context:current.context}:{})};
}
