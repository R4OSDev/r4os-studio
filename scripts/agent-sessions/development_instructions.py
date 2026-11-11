"""Guide the declared project development tools."""
from tool_catalog import tool_scope


def compose(config):
    if tool_scope(config) != 'project':
        return ''
    rights = config.get('permissions', {})
    text = ''
    if any(rights.get('studio.' + name) for name in ('build_project', 'deploy_project', 'run_project')):
        text += ('\n\nSTUDIO DEVELOPMENT: Build the project with its pins. For deployment, use the ready assigned VM '
                 'and the confirmed artifact. Launch explicitly with the returned deployment ID. Build, deploy and run '
                 'return their original result or readiness receipt. Verify the configured checks using the actual '
                 'application output, exit status or image. Complete a live test only after its required checks pass.')
    if rights.get('studio.read_development_job'):
        text += ('\n\nSTUDIO ORIGINAL JOB REFERENCES: Use studio_read_development_job with the returned jobId. '
                 'Use lookup={} to find original jobs, or filter by requestId or originRunId and toolCallId. '
                 'Read details and output with the returned cursors. Inspect the original job before acting on a lost reply.')
    if rights.get('studio.read_project_git'):
        text += ('\n\nSTUDIO GIT: Read the bound repository status and diff. Create an explicit reviewed selection '
                 'and use its selectionId for an authorized push. Check the original job after a lost push reply.')
    if rights.get('studio.run_vm_command'):
        text += ('\n\nSTUDIO PROJECT VM SSH: Use studio_run_vm_command for a native R4OS command on the running '
                 'assigned VM with development access. Keep each command within 112 UTF-8 bytes. Read the returned '
                 'job for stdout, stderr and confirmed exit status. Use the host terminal for host commands.')
    return text
