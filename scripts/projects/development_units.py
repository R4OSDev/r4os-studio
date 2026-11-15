"""Development worker identities shared by admission and deletion checks."""

LIFECYCLE_KINDS = ('vm_stop', 'vm_restart')
BUILD_UNIT = 'r4os-studio-development@{}.service'
VM_UNIT = 'r4os-studio-development-vm@{}.service'
SSH_UNIT = 'r4os-studio-development-ssh@{}.service'
LIFECYCLE_UNIT = 'r4os-studio-development-lifecycle@{}.service'
UNIT_PATTERNS = tuple(unit.format('*') for unit in (BUILD_UNIT, VM_UNIT, SSH_UNIT, LIFECYCLE_UNIT))


def job_units(job_id, kind='build'):
    if kind in LIFECYCLE_KINDS:
        # Already admitted jobs from older releases can still use the VM unit.
        return LIFECYCLE_UNIT.format(job_id), VM_UNIT.format(job_id)
    unit = SSH_UNIT if kind == 'ssh' else BUILD_UNIT if kind in ('build', 'package') else VM_UNIT
    return (unit.format(job_id),)


def job_unit(job_id, kind='build'):
    return job_units(job_id, kind)[0]
