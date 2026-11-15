#!/usr/bin/env python3
"""Package the full Guacamole kernel with the iOS-only shim and 90 Hz defaults."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time


def check_kernel(binary):
    # CI has older builds with some of these features. Check the actual Mach-O,
    # so an old artifact cannot accidentally be shipped as the full build.
    if not binary.startswith(bytes.fromhex("cffaedfe0c000001")):
        raise ValueError("Expected an ARM64 Mach-O")
    required = {
        "90 Hz panel mode": b"panel switched to 90 Hz",
        "NativeAdreno Metal bridge": b"SweetMetal2",
        "Bluetooth bridge": b"com.sweet.bt.host",
        "display refresh measurement": b"sweetfb_refresh",
    }
    missing = [name for name, marker in required.items() if marker not in binary]
    if missing:
        raise ValueError(f"Missing kernel features: {', '.join(missing)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-kernel", action="store_true", help="Verify the kernel without packaging")
    parser.add_argument("kernel", type=Path, help="Built kernel.development.sweet")
    parser.add_argument("stock_boot", type=Path, nargs="?", help="Boot image from the same phone for its DTB")
    parser.add_argument("output", type=Path, nargs="?", help="New output directory")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    kernel = args.kernel.resolve()

    binary = kernel.read_bytes()
    try:
        check_kernel(binary)
    except ValueError as error:
        parser.error(f"{kernel}: {error}")
    if args.check_kernel:
        if args.stock_boot or args.output:
            parser.error("--check-kernel takes only the kernel path")
        print(f"{kernel}: ARM64 kernel contains all required feature markers")
        return
    if args.stock_boot is None or args.output is None:
        parser.error("packaging requires stock_boot and output")
    stock_boot = args.stock_boot.resolve()
    output = args.output.resolve()
    stock_boot.stat()
    for name in ("a640_gmu.bin", "a630_sqe.fw", "a640_zap.mdt",
                 "a640_zap.b00", "a640_zap.b01", "a640_zap.b02"):
        if not (repo / "research/gpu/fw" / name).is_file():
            parser.error(f"Missing research/gpu/fw/{name}")
    if not (repo / "research/ipsw-x/d22ap.adt").is_file():
        parser.error("Missing research/ipsw-x/d22ap.adt")

    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, BOARD="guacamole", DUAL_BOOT="0")
    subprocess.run(["bash", str(repo / "shim/build.sh")], env=env, check=True)
    shim = repo / "shim/out/Image"
    adt = output / "guacamole.adt"
    subprocess.run([sys.executable, str(repo / "tools/mkadt.py"), str(adt),
                    "--highmem", "--guacamole"], check=True)

    common = (
        "debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress sweettouch=1 "
        "sweetkeys=1 sweetusb=0 wdt=-1 rd=ufsroot0 ufsroot=userdata "
        "unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin "
        "ufsrw=1 rootrw=1 launchd_unsecure_cache=1 sweetfb_noconsole=1 "
        "sweetlogdump=0 ufslogsecs=1 sweetaudio=0 "
        "sweetmailbox=1 sweetboxpart=rawdump sweetboxroot=1"
    )
    common += f" sweettime={int(time.time())}"
    variants = {
        "boot-corey-full-ios-90hz": "sweetfb90=1 sweetgpu=11 sweetmtl=2 sweetpmem=1 sweetbattery=2",
        "boot-corey-full-ios-60hz": "sweetfb90=0 sweetgpu=11 sweetmtl=2 sweetpmem=1 sweetbattery=2",
    }
    for name, options in variants.items():
        cmdline = f"{common} {options}"
        payload = output / f"{name}.payload"
        image = output / f"{name}.img"
        subprocess.run([sys.executable, str(repo / "tools/mkpayload.py"), str(kernel), str(adt),
                        str(payload), "--cmdline", cmdline], check=True)
        subprocess.run([sys.executable, str(repo / "tools/mkguacboot.py"), str(stock_boot), str(shim),
                        str(image), "--ramdisk", str(payload)], check=True)
        (output / f"{name}.boot-args.txt").write_text(cmdline + "\n")
    (output / "kernel.sha256").write_text(hashlib.sha256(binary).hexdigest() + "\n")


if __name__ == "__main__":
    main()
