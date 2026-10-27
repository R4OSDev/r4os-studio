import type { SessionItem } from '../../../../shared/agent-sessions';

function safeUrl(value: string | undefined) {
  if (!value || value.length > 2048 || /[\s\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function WebSearchCard({ value }: { value: SessionItem['webSearch'] }) {
  if (!value) return null;
  const url = safeUrl(value.url);
  const sources = value.sources?.slice(0, 24).flatMap((source) => {
    const href = safeUrl(source.url);
    return href ? [{ href, title: source.title.slice(0, 256) || href }] : [];
  }) ?? [];
  return <div className="agent-web-search">
    <p>{({ search: 'Search', openPage: 'Open page', findInPage: 'Find in page', other: 'Web action' })[value.action]}</p>
    {value.queries?.length ? <ul>{value.queries.slice(0, 8).map((query, index) => <li key={index}>{query.slice(0, 2048)}</li>)}</ul> : null}
    {url && <p><a href={url} target="_blank" rel="noopener noreferrer">{url}</a></p>}
    {value.pattern && <p>Find: {value.pattern.slice(0, 512)}</p>}
    {!!sources.length && <><p>Sources</p><ul>{sources.map((source) => <li key={source.href}><a href={source.href} target="_blank" rel="noopener noreferrer">{source.title}</a></li>)}</ul></>}
  </div>;
}
