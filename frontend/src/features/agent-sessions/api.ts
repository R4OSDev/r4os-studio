export function sessionPath(projectId: string, sessionId?: string) {
  return `/${encodeURIComponent(projectId)}/sessions${sessionId ? '/' + encodeURIComponent(sessionId) : ''}`;
}
export { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
export const busyRun = (state?: string) => ['queued', 'starting', 'running', 'stopping'].includes(state ?? '');
export const toolLabels: Record<string, string> = {
  'studio.exec_command': 'Run command', 'studio.write_stdin': 'Process input', 'studio.terminate_process': 'Terminate process',
  'studio.list_directory': 'List directory', 'studio.read_file': 'Read file', 'studio.search': 'Search',
  'studio.write_file': 'Write file', 'studio.apply_patch': 'Apply patch', 'studio.create_directory': 'Create directory',
};
