import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github';
import { projectRequest } from '../projects/api';
import { pullProject } from './projectApi';
import { bindingKey, openingCheck } from './openingCheck';

interface Opening { id: string | null; phase: 'checking' | 'prompt' | 'updating' | 'ready'; status?: GitHubProjectStatus; error?: string; notice?: string }
export function useProjectOpening(id: string | null, token: string) {
  const [value, setValue] = useState<Opening>({ id: null, phase: 'checking' });
  const [epoch,refresh]=useState(0),authenticated=Boolean(token),credential=useRef(token);
  if(value.id!==id)setValue({id,phase:'checking'});
  useLayoutEffect(()=>{credential.current=token;},[token]);
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController(), current = ++generation.current;
    const timer = window.setTimeout(() => {
      if (!id || !authenticated) return;
      setValue({ id, phase: 'checking' });
      void (async () => {
        try {
          const bound = await projectRequest<{ binding: GitHubProjectBinding | null }>(`/${id}/github`, '', 'GET', undefined, controller.signal);
          if (!bound.binding) { if (!controller.signal.aborted && generation.current === current) setValue({ id, phase: 'ready' }); return; }
          if(controller.signal.aborted)return;
          const status=await openingCheck(id,bound.binding,credential.current);
          if (controller.signal.aborted || generation.current !== current) return;
          setValue({ id, phase: status.behind > 0 && ['behind', 'diverged'].includes(status.state) ? 'prompt' : 'ready', status });
        } catch (e) {
          if (!controller.signal.aborted && generation.current === current) setValue({ id, phase: 'ready', notice: 'GitHub status unavailable: ' + (e as Error).message });
        }
      })();
    }, 0);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [id, authenticated,epoch]);
  async function update() {
    if (!id || value.id !== id || value.phase !== 'prompt' || !value.status) return;
    const current = generation.current, status = value.status;
    setValue({ ...value, phase: 'updating', error: '' });
    try {
      const currentBinding=await projectRequest<{binding:GitHubProjectBinding|null}>(`/${id}/github`);
      if(!status.binding||!currentBinding.binding||bindingKey(status.binding)!==bindingKey(currentBinding.binding))throw new Error('The repository connection changed. Ignore and refresh before updating.');
      const result = await pullProject(id, token, status);
      if (generation.current !== current) return;
      if (result.result && 'nothingApplied' in result.result && result.result.nothingApplied) throw new Error('No update was applied. Review the original operation in GitHub or choose Ignore.');
      setValue({ id, phase: 'ready' });
    } catch (e) { if (generation.current === current) setValue({ id, phase: 'prompt', status, error: (e as Error).message }); }
  }
  return {
    checking: !!id&&(value.id!==id||value.phase==='checking'),
    deciding: value.id === id && ['prompt', 'updating'].includes(value.phase),
    updating: value.id === id && value.phase === 'updating',
    status: value.id === id ? value.status : undefined,
    notice: value.id === id ? value.notice : '', error: value.id === id ? value.error : '',
    ignore: () => { if (id && value.id === id && value.phase === 'prompt') setValue({ id, phase: 'ready' }); },
    update,refresh:()=>{setValue({id,phase:'checking'});refresh(v=>v+1);},
  };
}
