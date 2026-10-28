import { useCallback, useEffect, useState } from 'react';
import type { Skill, SkillDetail } from '../../../../shared/skills';
import { loadSkills, request } from './api';
export function useSkills() {
  const [skills, setSkills] = useState<Skill[]>([]), [token, setToken] = useState(''), [error, setError] = useState('');
  const remember = (value: Skill) => setSkills((previous) => [...previous.filter((s) => s.id !== value.id), value].sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
  useEffect(() => {
    let cancelled = false;
    void loadSkills().then((value) => { if (!cancelled) { setSkills(value.skills); setToken(value.csrfToken); setError(''); } })
      .catch((cause: Error) => { if (!cancelled) setError(cause.message); });
    return () => { cancelled = true; };
  }, []);
  const reload = useCallback(async () => {
    try { const value = await loadSkills(); setSkills(value.skills); setToken(value.csrfToken); setError(''); }
    catch (cause) { setError((cause as Error).message); }
  }, []);
  useEffect(() => { const visible=()=>{if(!document.hidden)void reload();};const timer=window.setInterval(visible,5000);window.addEventListener('focus',visible);window.addEventListener('online',visible);document.addEventListener('visibilitychange',visible);return()=>{window.clearInterval(timer);window.removeEventListener('focus',visible);window.removeEventListener('online',visible);document.removeEventListener('visibilitychange',visible);}; }, [reload]);
  async function create(id: string, name: string) {
    const value = await request<SkillDetail>('POST', '', { id, name }, token); remember(value.skill); return value;
  }
  const forget=useCallback((id:string)=>setSkills(previous=>previous.filter(skill=>skill.id!==id)),[]);
  return { skills, token, error, reload, create, remember, forget };
}
