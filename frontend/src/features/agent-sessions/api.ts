export function sessionPath(projectId: string, sessionId?: string) {
  return `/${encodeURIComponent(projectId)}/sessions${sessionId ? '/' + encodeURIComponent(sessionId) : ''}`;
}
export { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
export const busyRun = (state?: string) => ['queued', 'starting', 'running', 'stopping'].includes(state ?? '');
export const toolLabels: Record<string, string> = {
  'studio.exec_command': 'Run command', 'studio.write_stdin': 'Process input', 'studio.terminate_process': 'Terminate process',
  'studio.list_directory': 'List directory', 'studio.read_file': 'Read file', 'studio.search': 'Search',
  'studio.write_file': 'Write file', 'studio.apply_patch': 'Apply patch', 'studio.create_directory': 'Create directory',
  'studio.build_project': 'Build project', 'studio.deploy_project': 'Deploy project', 'studio.run_project': 'Run project',
  'studio.read_development_job': 'Read development job', 'studio.stop_development_job': 'Stop development job',
  'studio.capture_vm': 'Capture VM', 'studio.send_vm_input': 'Send VM input',
  'studio.start_project_vm': 'Start project VM',
};
