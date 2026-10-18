#!/usr/bin/env python3
"""Install the pinned Linux app-build profile under App/Data (no emulator)."""

import argparse
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


APP = Path(__file__).resolve().parent.parent
PROFILE_FILE = APP / "shared/r4os/minimal-profile.json"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def install_component(root, name, component, archive_dir):
    destination = root / component["path"]
    marker = destination / ".studio-component.json"
    if destination.exists():
        if not marker.is_file() or json.loads(marker.read_text()) != component:
            raise RuntimeError(f"Existing {destination} has a different or missing installation record; refusing to overwrite it.")
        print(f"Already installed: {name} {component['version']}", flush=True)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=root) as staging:
        staging = Path(staging)
        # Optional local archives are still checked against the pinned SHA-256.
        archive = archive_dir / f"{name}.tar" if archive_dir else staging / "download.tar"
        if archive_dir:
            if not archive.is_file():
                raise RuntimeError(f"Missing local archive: {archive}")
        else:
            print(f"Downloading: {name} {component['version']}", flush=True)
            request = urllib.request.Request(component["url"], headers={"User-Agent": "R4OS-Studio-Setup"})
            with urllib.request.urlopen(request, timeout=60) as source, archive.open("wb") as target:
                shutil.copyfileobj(source, target)
        if digest(archive) != component["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch for {name}; package will not be installed.")

        unpacked = staging / "unpacked"
        unpacked.mkdir()
        with tarfile.open(archive, "r:*") as package:
            package.extractall(unpacked, filter="data")
        entries = list(unpacked.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise RuntimeError(f"Unexpected archive layout for {name}.")
        package_root = entries[0]
        required = "zig" if name == "zig" else "build.zig.zon"
        if not (package_root / required).is_file():
            raise RuntimeError(f"Missing {required} in {name} archive.")
        (package_root / ".studio-component.json").write_text(json.dumps(component, indent=2) + "\n")
        package_root.rename(destination)
    print(f"Installed: {destination}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, help="Use local zig.tar, sdk.tar, contract.tar archives instead of downloading.")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        parser.error("The pinned profile supports Linux x86_64 only.")
    os.umask(0o077)
    profile = json.loads(PROFILE_FILE.read_text())
    root = APP / "Data/R4OS"
    root.mkdir(parents=True, exist_ok=True)
    # Serialize setup attempts; never replace an existing installation in place.
    with (root / ".setup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for directory in ("Toolchains/Zig", "SDK", "Contract", "Libraries", "Images", "Instances", "Profiles"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (APP / "Data/Projects").mkdir(exist_ok=True)
        for name, component in profile["components"].items():
            install_component(root, name, component, args.archive_dir.resolve() if args.archive_dir else None)

        zig = root / profile["components"]["zig"]["path"] / "zig"
        version = subprocess.check_output([str(zig), "version"], text=True).strip()
        if version != profile["components"]["zig"]["version"]:
            raise RuntimeError(f"Unexpected Zig version: {version}")
        # Check the extracted package contents, including on repeated runs.
        # Keep fetch's working directory outside the package being checked:
        # Zig may stage a local package in cwd/zig-pkg before hashing it.
        with tempfile.TemporaryDirectory(prefix=".verify-", dir=root) as verification:
            verification = Path(verification)
            (verification / "build.zig").write_text('pub fn build(_: *@import("std").Build) void {}\n')
            environment = os.environ.copy()
            environment["ZIG_GLOBAL_CACHE_DIR"] = str(verification / "cache")
            for name in ("sdk", "contract"):
                component = profile["components"][name]
                result = subprocess.run([str(zig), "fetch", "--global-cache-dir", str(verification / "cache"),
                                         str(root / component["path"])], cwd=verification,
                                        env=environment, capture_output=True, text=True, check=True)
                package_hash = (result.stdout.strip() or result.stderr.strip())
                if package_hash != component["zigPackageHash"]:
                    raise RuntimeError(f"Package hash mismatch for {name}: {package_hash}")
                print(f"Verified package hash: {name}", flush=True)

        target = root / "Profiles/minimal.json"
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, prefix=".minimal-", delete=False) as temporary:
            temporary.write(json.dumps(profile, indent=2) + "\n")
        Path(temporary.name).replace(target)
        print(f"Ready: {target} (Zig {version}; no emulator installed)", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"R4OS setup failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        sys.exit(1)
