#!/usr/bin/env bash
set -euo pipefail
SCRIPTS_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIRECTORY="$(cd -- "$SCRIPTS_DIRECTORY/.." && pwd)"
if [[ $EUID -ne 0 ]]; then
    printf 'Run this host installer as root.\n' >&2
    exit 1
fi
for command in qemu-system-x86_64 qemu-img mkfs.fat mcopy mdir; do
    command -v "$command" >/dev/null || { printf 'Missing host dependency: %s\n' "$command" >&2; exit 1; }
done
getent passwd r4os-studio >/dev/null
NODE_BINARY="$(readlink -f -- "$(command -v node)")"
"$NODE_BINARY" --input-type=module - "$SCRIPTS_DIRECTORY/updates/systemd/r4os-studio-vm@.service.in" "$APP_DIRECTORY" "$NODE_BINARY" > /etc/systemd/system/r4os-studio-vm@.service <<'JS'
import { readFileSync } from 'node:fs';
const [, , template, app, node] = process.argv;
function escape(value) {
  if (/[\r\n]/.test(value)) throw new Error('Unsupported path');
  return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('%', '%%');
}
process.stdout.write(readFileSync(template, 'utf8').replaceAll('@APP_DIRECTORY@', escape(app)).replaceAll('@NODE_BINARY@', escape(node)));
JS
install -d -m 0755 /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/49-r4os-studio-vms.rules <<'JS'
polkit.addRule(function(action, subject) {
    if (action.id === "org.freedesktop.systemd1.manage-units" && subject.user === "r4os-studio") {
        var unit = action.lookup("unit");
        var verb = action.lookup("verb");
        if (unit && /^r4os-studio-vm@[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\.service$/.test(unit)
            && (verb === "start" || verb === "stop")) return polkit.Result.YES;
    }
});
JS
chmod 0644 /etc/polkit-1/rules.d/49-r4os-studio-vms.rules
# Keep the immutable worker dispatcher when update support is configured.
if [[ -f /etc/r4os-studio-updates/config.json ]]; then
    python3 - <<'PYVM'
from pathlib import Path
import re
p = Path('/etc/systemd/system/r4os-studio-vm@.service')
s = p.read_text()
s = re.sub(r'^ExecStart=.*$', 'ExecStart=/usr/bin/python3 /opt/r4os-studio/bin/vm-dispatch.py %i', s, flags=re.M)
s = re.sub(r'^ExecStopPost=.*$', 'ExecStopPost=/usr/bin/python3 /opt/r4os-studio/bin/vm-dispatch.py %i --sync', s, flags=re.M)
p.write_text(s)
PYVM
fi
install -d -m 0700 -o r4os-studio -g r4os-studio "$APP_DIRECTORY/Data/R4OS/Instances" "$APP_DIRECTORY/Data/R4OS/Images"
printf 'd /run/r4os-studio-vms 0700 r4os-studio r4os-studio -\n' > /etc/tmpfiles.d/r4os-studio-vms.conf
systemd-tmpfiles --create /etc/tmpfiles.d/r4os-studio-vms.conf
systemd-analyze verify /etc/systemd/system/r4os-studio-vm@.service
systemctl daemon-reload
printf 'VM host support installed. Reinstall/restart the Studio service after building.\n'
