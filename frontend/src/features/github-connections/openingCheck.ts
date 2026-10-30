import type { GitHubJob, GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github';
import { projectRequest, projectRequestId } from '../projects/api';
import { waitGitJob } from './projectApi';

// A view leaving does not cancel a shared read or its original accepted job.
// Only pending promises are retained; reopening after completion checks again.
const pending=new Map<string,Promise<GitHubProjectStatus>>();
export const bindingKey=(binding:GitHubProjectBinding)=>JSON.stringify([binding.revision,binding.connectionId,binding.userId,binding.repository.id,binding.repository.owner,binding.repository.name,binding.branch]);
export const pendingOpeningCheck=(id:string,binding:GitHubProjectBinding)=>pending.get(id+':'+bindingKey(binding));
export function openingCheck(id:string,binding:GitHubProjectBinding,token:string) {
  const key=id+':'+bindingKey(binding),existing=pending.get(key);if(existing)return existing;
  if(pending.size>=8)return Promise.reject(new Error('Background GitHub checks are busy. Refresh the remote status shortly.'));
  const request=(async()=>{
    const accepted=await projectRequest<GitHubJob>(`/${id}/github/jobs`,token,'POST',{requestId:projectRequestId(),kind:'check',input:{bindingRevision:binding.revision}});
    if(accepted.projectId!==id||accepted.kind!=='check')throw new Error('The original GitHub check could not be matched.');
    const job=await waitGitJob(id,accepted.id,accepted);
    if(job.state!=='completed'||!job.result||!('snapshot' in job.result)||!job.result.binding||!job.result.fresh||!job.result.checkedAt||bindingKey(job.result.binding)!==bindingKey(binding))throw new Error(job.error??'The current repository could not be checked.');
    // The binding may have changed while the worker was checking the remote.
    const current=await projectRequest<{binding:GitHubProjectBinding|null}>(`/${id}/github`);
    if(!current.binding||bindingKey(current.binding)!==bindingKey(binding))throw new Error('The repository connection changed. Refresh its remote status.');
    return job.result;
  })();
  pending.set(key,request);
  void request.finally(()=>{if(pending.get(key)===request)pending.delete(key);}).catch(()=>undefined);
  return request;
}
