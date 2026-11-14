import type { GitHubProjectBinding } from '../../../../shared/project-github.js';
import { GitHubApi } from '../github-connections/repositories.js';
import { GitHubStore } from '../github-connections/store.js';
import { ProjectError } from '../projects/store.js';
import { bindingKey } from './observations.js';

const QUERY = `query StudioIssue($owner:String!,$name:String!,$number:Int!){
  viewer{databaseId} repository(owner:$owner,name:$name){databaseId nameWithOwner hasIssuesEnabled
    issue(number:$number){id number title body url state stateReason viewerCanClose}
  }
}`;

type Detail = {
  id: string; number: number; title: string; body: string; url: string;
  state: 'OPEN' | 'CLOSED'; stateReason: string | null; viewerCanClose: boolean;
};
type Response = {
  errors?: unknown[];
  data?: { viewer?: { databaseId?: number }; repository?: { databaseId?: number; nameWithOwner?: string; hasIssuesEnabled?: boolean; issue?: Detail } };
};

export class ProjectIssueTarget {
  constructor(private store: GitHubStore, private binding: (id: string) => Promise<GitHubProjectBinding | null>, private transport: typeof fetch) {}

  async read(projectId: string, number: number, revision: number, credentialRevision: number) {
    const bound = await this.binding(projectId);
    if (!bound || bound.revision !== revision) throw new ProjectError('The repository changed. Refresh its issues.', 409);
    const credential = await this.store.credential(bound.connectionId, credentialRevision);
    const api = new GitHubApi(credential.token, this.transport);
    const assertCurrent = async () => {
      const value = await this.binding(projectId);
      if (!value || bindingKey(value) !== bindingKey(bound)) throw new ProjectError('The repository changed. Refresh its issues.', 409);
      await this.store.assertCredential(bound.connectionId, credentialRevision);
    };
    await assertCurrent();
    const result = await api.request('/graphql', 'POST', { operationName: 'StudioIssue', query: QUERY,
      variables: { owner: bound.repository.owner, name: bound.repository.name, number } }) as Response;
    await assertCurrent();
    if (!result || typeof result !== 'object' || (result.errors !== undefined && (!Array.isArray(result.errors) || result.errors.length))) {
      throw new ProjectError('GitHub could not confirm the selected issue. Check access and refresh the list.', 502);
    }
    const repository = result.data?.repository;
    if (result.data?.viewer?.databaseId !== bound.userId) throw new ProjectError('The GitHub account changed.', 409);
    if (repository?.databaseId !== bound.repository.id || repository?.nameWithOwner?.toLowerCase() !== bound.repository.fullName.toLowerCase()) {
      throw new ProjectError('The GitHub repository could not be matched.', 409);
    }
    if (repository.hasIssuesEnabled !== true) throw new ProjectError('GitHub Issues are unavailable for this repository.', 422);
    const issue = repository.issue;
    if (!issue) throw new ProjectError('The selected GitHub issue is unavailable.', 404);
    if (issue.number !== number || typeof issue.id !== 'string' || !/^[A-Za-z0-9_+/=-]{1,256}$/.test(issue.id)
        || typeof issue.title !== 'string' || !issue.title.trim() || typeof issue.body !== 'string'
        || issue.url !== 'https://github.com/' + repository.nameWithOwner + '/issues/' + number
        || !['OPEN', 'CLOSED'].includes(issue.state) || typeof issue.viewerCanClose !== 'boolean'
        || !(issue.stateReason === null || typeof issue.stateReason === 'string')) {
      throw new ProjectError('GitHub returned invalid issue data.', 502);
    }
    return { bound, issue, api, assertCurrent };
  }
}

export function roadmapIssueText(value: string, maximumBytes: number, suffix = '…') {
  const text = value.replace(/[\p{Cs}\p{Cc}]/gu, character => {
    const code = character.codePointAt(0)!;
    return code === 9 || code === 10 || code === 13 || (code >= 128 && code < 160) ? character : '\uFFFD';
  });
  if (Buffer.byteLength(text) <= maximumBytes) return text;
  let prefix = '', bytes = Buffer.byteLength(suffix);
  for (const character of text) {
    bytes += Buffer.byteLength(character);
    if (bytes > maximumBytes) break;
    prefix += character;
  }
  return prefix + suffix;
}
