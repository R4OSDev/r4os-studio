"""Service configuration for Studio's trusted, single-root host model."""
# Resource controls and process lifecycle settings intentionally remain intact.
ISOLATION_KEYS = {
    'User', 'Group', 'DynamicUser', 'SupplementaryGroups',
    'ProtectSystem', 'ProtectHome', 'PrivateTmp', 'PrivateDevices',
    'PrivateNetwork', 'PrivateUsers', 'PrivateMounts', 'PrivateIPC',
    'NoNewPrivileges', 'CapabilityBoundingSet', 'AmbientCapabilities',
    'ProtectKernelTunables', 'ProtectKernelModules', 'ProtectKernelLogs',
    'ProtectControlGroups', 'ProtectClock', 'ProtectHostname', 'ProtectProc',
    'ProcSubset', 'RestrictSUIDSGID', 'RestrictNamespaces',
    'RestrictAddressFamilies', 'RestrictRealtime', 'LockPersonality',
    'SystemCallFilter', 'SystemCallArchitectures', 'MemoryDenyWriteExecute',
    'ReadWritePaths', 'ReadOnlyPaths', 'InaccessiblePaths',
    'BindPaths', 'BindReadOnlyPaths', 'TemporaryFileSystem',
    'RootDirectory', 'RootImage', 'NetworkNamespacePath',
    'DevicePolicy', 'DeviceAllow', 'IPAddressAllow', 'IPAddressDeny',
}


def root_service(text, identity=True):
    """Remove obsolete unit isolation; retain commands, limits and local options."""
    result = []
    for line in text.splitlines():
        if line.partition('=')[0].strip() in ISOLATION_KEYS:
            continue
        result.append(line)
        if identity and line.strip() == '[Service]':
            result.extend(('User=root', 'Group=root'))
    return '\n'.join(result) + '\n'


def service_units(directory):
    return sorted(path for path in directory.glob('r4os-studio*.service') if path.is_file())
