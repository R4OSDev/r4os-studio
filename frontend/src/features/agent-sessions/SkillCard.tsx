export function SkillCard({ value }: { value: unknown }) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const data = value as Record<string, unknown>;
  if (typeof data.validated !== 'boolean' || typeof data.saved !== 'boolean' || !Array.isArray(data.errors)) return null;
  const saved = data.saved && Number.isSafeInteger(data.activeRevision) && typeof data.activeHash === 'string' && /^[a-f0-9]{64}$/.test(data.activeHash);
  return <div className="agent-skill-result">
    <p>{saved ? `Saved skill revision ${data.activeRevision}.` : data.validated ? 'Skill draft validated.' : 'Skill draft needs changes.'}</p>
    {saved && <p>SHA-256: <code>{String(data.activeHash)}</code></p>}
    {data.errors.length > 0 && <ul>{data.errors.filter((error): error is string => typeof error === 'string').slice(0, 20).map((error, index) => <li key={index}>{error}</li>)}</ul>}
  </div>;
}
