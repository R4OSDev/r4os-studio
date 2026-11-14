import { createContext, useContext, useMemo } from 'react';
import { ProjectRequestError, studioRequest } from '../projects/api';
import type {AgentToolId} from '../../../../shared/agent-sessions';
import { sharedSessionRead, shareSessionPath } from './sessionReads';
export function sessionPath(projectId: string, sessionId?: string) {
  return `/${encodeURIComponent(projectId)}/sessions${sessionId ? '/' + encodeURIComponent(sessionId) : ''}`;
}
export { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
export const isLocalReadBusy = (error: unknown) => error instanceof ProjectRequestError && error.status === 429
  && error.message === 'Local readers are busy. Try this read again shortly.';
export const busyRun = (state?: string) => ['queued', 'starting', 'running', 'stopping'].includes(state ?? '');
export const permissionToolLabels: Record<AgentToolId, string> = {
  'studio.skill_discover':'Discover skill tools', 'studio.skill_call':'Call skill tool', 'studio.read_skill_result':'Read skill result',
  'studio.exec_command': 'Run command', 'studio.write_stdin': 'Process input', 'studio.terminate_process': 'Terminate process',
  'studio.list_directory': 'List directory', 'studio.read_file': 'Read file', 'studio.search': 'Search',
  'studio.read_attachment': 'Read attachment', 'studio.read_context_result':'Read original context result',
  'studio.generate_image':'Generate image', 'studio.list_generated_images': 'List generated images', 'studio.import_generated_image': 'Import generated image',
  'studio.write_file': 'Write file', 'studio.apply_patch': 'Apply patch', 'studio.create_directory': 'Create directory',
  'studio.build_project': 'Build project', 'studio.deploy_project': 'Deploy project', 'studio.run_project': 'Run project',
  'studio.complete_development_job': 'Complete checks',
  'studio.read_development_job': 'Read development job', 'studio.stop_development_job': 'Stop development job',
  'studio.capture_vm': 'Capture VM', 'studio.send_vm_input': 'Send VM input',
  'studio.control_app_window': 'Control app window',
  'studio.start_project_vm': 'Start project VM', 'studio.stop_project_vm':'Stop project VM', 'studio.restart_project_vm':'Restart project VM', 'studio.run_vm_command': 'Run VM SSH command',
  'studio.push_project': 'Push project to GitHub',
  'studio.read_project_git': 'Read Git status, diff and jobs',
  'studio.finish_github_issue': 'Finish linked GitHub issues',
  'studio.get_remote_host': 'Remote Host information', 'studio.run_remote_command': 'Run remote command',
  'studio.remote_files': 'Remote files', 'studio.read_remote_job': 'Read remote job', 'studio.stop_remote_job': 'Stop remote job',
  'studio.read_update_package': 'Read update packages', 'studio.plan_update_package': 'Plan update package',
  'studio.build_update_package': 'Build update package', 'studio.check_update_vm': 'Check update VM',
  'studio.upload_update_package': 'Upload update package', 'studio.install_update_package': 'Install or stage update',
  'studio.commit_update': 'Commit update and reboot', 'studio.verify_update': 'Verify installed update',
  'studio.resume_update': 'Resume own update', 'studio.abort_update': 'Abort prepared update',
  'studio.rollback_update': 'Roll back last update', 'studio.cleanup_update_transport': 'Clean own update transport',
  'studio.validate_skill': 'Validate skill', 'studio.save_skill': 'Save skill',
};
export const permissionToolIds=Object.keys(permissionToolLabels) as AgentToolId[];
// Transcript labels may include native tools and grouped feature operations.
// They are deliberately separate from independently saved permission keys.
export const toolLabels:Record<string,string>={...permissionToolLabels,
  'studio.read_environment_notes':'Read environment notes','studio.record_environment_note':'Record environment note',
  'image_gen.imagegen':'Generate image','studio.web_search':'Web access'};

export const SessionScope = createContext<'project' | 'skill'>('project');
export function useSessionApi() {
  const scope = useContext(SessionScope);
  return useMemo(() => {
    const base = scope === 'skill' ? '/api/skills' : '/api/projects';
    return { scope, base, request: <T>(path: string, token = '', method = 'GET', body?: unknown, signal?: AbortSignal) => method === 'GET' && shareSessionPath(path)
      ? sharedSessionRead(base, path, sharedSignal => studioRequest<T>(base,path,token,method,body,sharedSignal), signal)
      : studioRequest<T>(base, path, token, method, body, signal) };
  }, [scope]);
}

export const updateToolIds = ['studio.read_update_package', 'studio.plan_update_package', 'studio.build_update_package',
  'studio.check_update_vm', 'studio.upload_update_package', 'studio.install_update_package', 'studio.commit_update',
  'studio.verify_update', 'studio.resume_update', 'studio.abort_update', 'studio.rollback_update', 'studio.cleanup_update_transport'];
export const remoteToolIds = ['studio.get_remote_host', 'studio.run_remote_command', 'studio.remote_files', 'studio.read_remote_job', 'studio.stop_remote_job'];

export const imageToolIds = ['studio.generate_image', 'studio.list_generated_images', 'studio.import_generated_image'];
