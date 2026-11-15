#!/usr/bin/env python3
"""Install the full Corey userland on a mounted clean iOS 16.7.16 image."""

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import stat


def load_tool(directory, filename):
    spec = importlib.util.spec_from_file_location(filename, directory / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("userland", type=Path, help="Signed iOS binaries and SweetMetal2 bundle")
    parser.add_argument("--radio-firmware", type=Path, help="Phone firmware tree containing modem, rmtfs and bt")
    parser.add_argument("--ssh-bootstrap", type=Path, help="Configured Procursus /var/jb tree with SSH")
    args = parser.parse_args()
    root = args.root.resolve()
    binaries = args.userland.resolve()
    firmware = args.radio_firmware.resolve() if args.radio_firmware else None
    bootstrap = args.ssh_bootstrap.resolve() if args.ssh_bootstrap else None
    if not os.path.ismount(root):
        parser.error(f"Expected a mounted iOS root at {root}")
    tools = Path(__file__).resolve().parent
    gl = load_tool(tools, "install-gl-root.py")
    tweaks = load_tool(tools, "sweet-root-tweaks.py")
    version = gl.load_plist(root / "System/Library/CoreServices/SystemVersion.plist")
    if (version["ProductVersion"], version["ProductBuildVersion"]) != ("16.7.16", "20H392"):
        parser.error("Expected iOS 16.7.16 (20H392)")

    files = dict(gl.FILES)
    files["libsweet-glapp.dylib"] = "usr/lib/libsweet-glapp.dylib"
    files["sweet-autorun"] = "usr/libexec/sweet-autorun"
    for name in ("wland", "btbridge", "sweet-displayd", "sweet-containers", "sweet-sysapps"):
        files[name] = f"private/var/local/bin/{name}"
    audio = "System/Library/Audio/Plug-Ins/HAL/HakiosAudio.driver"
    metal = "System/Library/Extensions/SweetMetal2.bundle"
    files.update({
        "HakiosAudio": f"{audio}/HakiosAudio",
        "HakiosAudio.plist": f"{audio}/Info.plist",
        "SweetMetal2.bundle/SweetMetal2": f"{metal}/SweetMetal2",
        "SweetMetal2.bundle/Info.plist": f"{metal}/Info.plist",
        "SweetMetal2.bundle/libvulkan_freedreno.dylib": f"{metal}/libvulkan_freedreno.dylib",
    })
    required = [binaries / filename for filename in files]
    if firmware:
        required.extend(firmware / "modem" / name for name in (
            "modem.mdt", "modem.b00", "modemr.jsn", "modemuw.jsn", "wlanmdsp.mbn", "bdwlan.b0e",
        ))
        required.extend(firmware / "rmtfs" / f"{name}.img" for name in ("modemst1", "modemst2", "fsg", "fsc"))
        required.extend((firmware / "bt/crbtfw21.tlv", firmware / "bt/crnv21.bin"))
    if bootstrap:
        required.append(bootstrap / "usr/sbin/sshd")
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        parser.error("Missing inputs:\n" + "\n".join(missing))
    for filename, path in files.items():
        source = binaries / filename
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = 0o644 if filename.endswith(".plist") else 0o755
        gl.install_file(source, target, 0, 0, mode)
        if source.read_bytes() != target.read_bytes():
            raise SystemExit(f"Installed bytes differ at /{path}")
    private = root / "private/var"
    if firmware:
        for name in ("modem", "rmtfs", "bt"):
            target = private / "local/fw" / name
            target.mkdir(parents=True, exist_ok=True)
            target.chmod(0o700)
            for source in (firmware / name).iterdir():
                if source.is_file() and not source.is_symlink():
                    gl.install_file(source, target / source.name, 0, 0, 0o600)
    if bootstrap:
        subprocess.run(["rsync", "-aH", "--numeric-ids", str(bootstrap) + "/", str(private / "jb") + "/"], check=True)
        if not os.access(private / "jb/usr/sbin/sshd", os.X_OK):
            raise SystemExit("Installed Procursus sshd must be executable")
    clients = private / "local/mtl2-clients"
    clients.write_text("backboardd\ncom.apple.WebKit.GPU\ncom.apple.WebKit.WebContent\n")
    clients.chmod(0o644)
    tweaks.merge_pref(root, ".GlobalPreferences", {
        "CAEnableDeepFramebuffer": False,
        "CAEnableFramebufferCompression": False,
        "CAEnableIOSurfaceCompression": False,
        "WebKit2GPUProcessForDOMRendering": False,
    })
    # Reuse the upstream launchd job definitions. Gate each job on its files.
    config = root / "System/Library/xpc/launchd.plist"
    tweaks.launchd_plist(str(config), str(config))
    launchd = gl.load_plist(config)
    jobs = launchd["LaunchDaemons"]
    enabled = {"com.sweet.containers", "com.sweet.displayd"}
    if firmware:
        enabled.update(("com.sweet.wland", "com.sweet.btbridge"))
    if bootstrap:
        enabled.add("com.sweet.sshd")
    for key, job in tweaks.NET_JOBS.items():
        if job["Label"] in enabled:
            jobs[key] = job
        else:
            jobs.pop(key, None)
    metadata = config.stat()
    tweaks.save(config, launchd, metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))
    print("Enabled services: " + ", ".join(sorted(enabled)))


if __name__ == "__main__":
    main()
