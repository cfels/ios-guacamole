#!/usr/bin/env python3
"""Install the working Corey OpenGL libraries into a mounted fresh iOS root."""

import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import stat
import tempfile


FILES = {
    "libOSMesa.8.dylib": "usr/lib/libOSMesa.8.dylib",
    "libsweet-gl.dylib": "usr/lib/libsweet-gl.dylib",
    "libsweet-bbd.dylib": "usr/lib/libsweet-bbd.dylib",
    "sweet-bbd": "usr/libexec/sweet-bbd",
}
BACKBOARDD = "/usr/libexec/backboardd"
WRAPPER = "/usr/libexec/sweet-bbd"


def load_plist(path):
    with path.open("rb") as file:
        return plistlib.load(file)


def install_file(source, target, owner, group, mode):
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
        staging = Path(file.name)
        try:
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, file)
            file.close()
            os.chown(staging, owner, group)
            staging.chmod(mode)
            staging.replace(target)
        finally:
            staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("libraries", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if not os.path.ismount(root):
        raise SystemExit(f"Expected a mounted iOS root at {root}")
    version = load_plist(root / "System/Library/CoreServices/SystemVersion.plist")
    if (version["ProductVersion"], version["ProductBuildVersion"]) != ("16.7.16", "20H392"):
        raise SystemExit("This OpenGL bridge is pinned to iOS 16.7.16 (20H392)")

    config = root / "System/Library/xpc/launchd.plist"
    launchd = load_plist(config)
    matches = [job for job in launchd["LaunchDaemons"].values()
               if job.get("Label") == "com.apple.backboardd"]
    if len(matches) != 1 or "Program" in matches[0]:
        raise SystemExit("Unexpected backboardd launch configuration")
    job = matches[0]
    if job["ProgramArguments"] not in ([BACKBOARDD], [WRAPPER]):
        raise SystemExit("Unexpected backboardd ProgramArguments")
    if any(job.get("Label") == "com.sweet.autorun" for job in launchd["LaunchDaemons"].values()):
        raise SystemExit("Expected the clean root without the SWEETBOX test job")
    for name, path in FILES.items():
        source, target = args.libraries / name, root / path
        with source.open("rb") as file:
            if file.read(8) != bytes.fromhex("cffaedfe0c000001"):
                raise SystemExit(f"Expected an ARM64 Mach-O at {source}")
        if target.parent.resolve() != target.parent or not target.parent.is_dir():
            raise SystemExit(f"Unexpected target directory {target.parent}")

    for name, path in FILES.items():
        source, target = args.libraries / name, root / path
        install_file(source, target, 0, 0, 0o755)
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise SystemExit(f"Installed bytes differ at {target}")
        print(f"Verified /{path}")
    if job["ProgramArguments"] != [WRAPPER]:
        metadata = config.stat()
        job["ProgramArguments"] = [WRAPPER]
        with tempfile.TemporaryDirectory() as directory:
            modified = Path(directory) / "launchd.plist"
            modified.write_bytes(plistlib.dumps(launchd, fmt=plistlib.FMT_BINARY))
            install_file(modified, config, metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))
    if load_plist(config) != launchd:
        raise SystemExit("Installed launchd configuration differs from expected")
    print("Verified backboardd launch configuration")


if __name__ == "__main__":
    main()
