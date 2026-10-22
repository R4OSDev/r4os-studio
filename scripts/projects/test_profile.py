from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdk import profile


class SelectedProfile(unittest.TestCase):
    def test_unregistered_future_revisions_and_compiler_are_selected_but_pins_still_bind_bytes(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            root = Path(temporary); projects = root / 'Projects'; projects.mkdir()
            sdk, contract = 'a' * 40, 'b' * 40
            for kind, key in [('SDK', sdk), ('Contract', contract), ('Toolchains/Zig', '99.1.2')]:
                path = root / kind / key; path.mkdir(parents=True)
                (path / '.studio-component.json').write_text(json.dumps({'version': '99.1.2', 'revision': key if kind != 'Toolchains/Zig' else None,
                    'sha256': 'c' * 64, 'url': 'https://example.invalid/archive', 'packageHash': 'sdk-hash' if kind == 'SDK' else 'contract-hash'}))
            (root / 'SDK' / sdk / 'build.zig.zon').write_text('.{ .version = "99.1.2", .dependencies = .{ .r4os_contract = .{ .url = "https://github.com/R4OSDev/r4os-contract/archive/' + contract + '.tar.gz", .hash = "contract-hash" } } }')
            binary = root / 'Toolchains/Zig/99.1.2/zig'; binary.write_bytes(b'compiler fixture')
            (root / 'Profiles').mkdir(); (root / 'Profiles/versions.json').write_text(json.dumps({'defaults': {'sdk': {'revision': sdk}, 'contract': {'revision': contract}, 'zig': {'version': '99.1.2'}}}))
            patches.enter_context(patch('sdk.run', side_effect=lambda args, env: '99.1.2' if args[1] == 'version' else ('sdk-hash' if args[2] == root / 'SDK' / sdk else 'contract-hash')))
            patches.enter_context(patch('toolset.prepare', return_value={'pin': {'releaseSha256': 'd' * 64}, 'capabilities': {}, 'catalog': root / 'catalog'}))
            patches.enter_context(patch('rust_projects.runner', return_value=None))
            selected = profile(root, projects, resolve_rust=False)
            self.assertEqual(selected['pins']['sdk']['revision'], sdk)
            self.assertEqual(selected['pins']['zig']['version'], '99.1.2')
            self.assertEqual(selected['pins']['zig']['binarySha256'], hashlib.sha256(b'compiler fixture').hexdigest())
            binary.write_bytes(b'changed compiler')
            with self.assertRaisesRegex(ValueError, 'Pinned project components changed'):
                profile(root, projects, selected['pins'], resolve_rust=False)
            binary.write_bytes(b'compiler fixture')
            marker = root / 'Contract' / contract / '.studio-component.json'; value = json.loads(marker.read_text()); value['packageHash'] = 'wrong-contract'; marker.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'selected Contract differs'):
                profile(root, projects, resolve_rust=False)


if __name__ == '__main__': unittest.main()
