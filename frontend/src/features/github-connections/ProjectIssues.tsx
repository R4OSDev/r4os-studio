import {Icon} from '../../app/Icon';
import type {GitHubIssueState, GitHubIssueCount} from '../../../../shared/project-github-issues';
import type {ProjectIssuesModel} from './useProjectIssues';
import {issueCountText} from './useIssueCounts';
import './issues.css';

export function GithubNavigation({model,count,selected,disabled,choose}:{model:ProjectIssuesModel;count?:GitHubIssueCount;selected:'Connection'|'Issues';disabled:boolean;choose:(view:'Connection'|'Issues')=>void}){
  const label=count?issueCountText(count):model.loading?'Loading open issue count':'Open issue count unavailable';
  return <nav className="nav-column" aria-label="Project GitHub sections"><div className="nav-items">
    <button type="button" disabled={disabled} className={`nav-item ${selected==='Connection'?'selected':''}`} aria-current={selected==='Connection'?'page':undefined} onClick={()=>choose('Connection')}><Icon name="settings"/><span>Connection</span></button>
    <button type="button" disabled={disabled||!model.binding} className={`nav-item github-issues-navigation ${selected==='Issues'?'selected':''}`} aria-current={selected==='Issues'?'page':undefined} title={!model.binding?'Connect a repository first.':undefined} onClick={()=>choose('Issues')}><Icon name="book"/><span>Issues</span><span className="github-issues-count" aria-label={label} title={label}>{count?.count!=null?(count.state==='stale'?'~':'')+count.count:count?.state==='unknown'||model.loading?'…':'—'}</span></button>
  </div></nav>;
}

export function ProjectIssues({model}:{model:ProjectIssuesModel}){
  const data=model.data;
  return <section className="project-issues" aria-label="GitHub Issues">
    <header><div><h2>Issues</h2>{model.binding&&<p>{model.binding.repository.fullName}</p>}</div><div className="github-issues-actions">
      <label>Show<select aria-label="Issue state" value={model.state} onChange={e=>model.filter(e.target.value as GitHubIssueState)}><option value="open">Open</option><option value="closed">Closed</option><option value="all">All</option></select></label>
      <button type="button" disabled={model.loading} onClick={model.refresh}>Refresh</button>
    </div></header>
    {model.loading&&<p role="status">Loading issues…</p>}
    {!data&&!model.loading&&!model.error&&model.binding&&<p className="github-issues-empty">Issues have not been checked yet. Select Refresh to load them now.</p>}
    {model.error&&<div className="github-issues-error" role="alert"><p>{model.error}</p><button type="button" onClick={model.refresh}>Retry from first page</button></div>}
    {data&&<>
      {data.refreshError&&<p className="github-issues-error" role="status">{data.refreshError}</p>}
      <p className="github-issues-checked" role="status">{model.stale?'Last checked data. Refresh for a current view. ':data.cached?'Cached. ':''}Checked {new Date(data.checkedAt).toLocaleString()} · {data.openCount} open issue{data.openCount===1?'':'s'} across this repository.</p>
      {data.items.length?<ol className="github-issues-list">{data.items.map(issue=><li key={issue.number} className="github-issue">
        <div className="github-issue-heading"><span className={`github-issue-state ${issue.state}`}>{issue.state==='open'?'Open':'Closed'}</span><a href={issue.url} target="_blank" rel="noopener noreferrer"><span>#{issue.number}</span> {issue.title}</a></div>
        {issue.labels.length>0&&<div className="github-issue-labels">{issue.labels.map((label,index)=><span key={index} style={{borderColor:'#'+label.color}}>{label.name}</span>)}{issue.moreLabels>0&&<span>+{issue.moreLabels} more</span>}</div>}
        <time dateTime={issue.updatedAt}>Updated {new Date(issue.updatedAt).toLocaleString()}</time>
      </li>)}</ol>:<p className="github-issues-empty">No {model.state==='all'?'':model.state+' '}issues found.</p>}
      <footer className="github-issues-paging"><button type="button" disabled={model.loading||!model.canPrevious} onClick={model.previous}>Previous</button><button type="button" disabled={model.loading||!data.nextCursor} onClick={model.next}>Next</button></footer>
    </>}
  </section>;
}
